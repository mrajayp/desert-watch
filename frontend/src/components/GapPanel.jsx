import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, dwell, qs } from '../api'
import { useApp } from '../App'
import { MixBar } from '../charts/Balance'
import { DIMENSIONS, LENS_TEXT, fmt, gapLabel } from '../charts/scales'
import { about, weekEnd, weekRange } from '../charts/trendText'
import { useApi } from '../hooks/useApi'
import { useDraft } from '../hooks/useDraft'
import { useMutation } from '../hooks/useMutation'
import { usePageTitle } from '../hooks/usePageTitle'
import { fmtDate, t } from '../i18n'
import { articlesPath, gapPath } from '../routes'
import Comments from './Comments'
import ArticleRow from './ArticleRow'
import BlindSpots from './BlindSpots'
import CopyLink from './CopyLink'
import Dialog from './Dialog'
import { ErrorBox, Loading } from './Notices'
import SourceFilter from './SourceFilter'
import SearchTerms from './SearchTerms'
import { WarningPills } from './Warnings'

const N_ = (s) => s // marks English for the catalogue; translated with t() when shown

const VOTES = [
  ['real', N_('Real gap'), N_('This is under-reported and worth covering')],
  ['covered', N_('Already covered'), N_('Paste the link — it will count as coverage')],
  ['not_newsworthy', N_('Not newsworthy'), N_('The signal is real but not a story')],
]
// vote and claim codes from the API, shown as they read in English
const VOTE_CODE = { real: N_('real'), covered: N_('covered'), not_newsworthy: N_('not newsworthy') }
const CLAIM_STATUS = { working: N_('working'), published: N_('published'), dropped: N_('dropped') }

// One gap: /gaps/:themeId/:regionId?lens=&week=. A dialog over the page from 900px up, a page below.
export default function GapPanel({ themeId, regionId, week: weekProp, lens: lensProp }) {
  const { meta, filters: f0, lang, closePanel, refresh, openAdd, can } = useApp()
  // a chart can open the panel at a given week/lens without changing the page-wide filters
  const filters = { ...f0, lens: lensProp || f0.lens, week: weekProp || f0.week }
  // the vote note survives a language switch or a detour to another panel (sessionStorage)
  const [voteNote, setVoteNote, clearVoteNote] = useDraft(`vote:${themeId}:${regionId}`)
  const [coveredUrl, setCoveredUrl] = useState('')
  const [pending, setPending] = useState(null)
  const [claimUrl, setClaimUrl] = useState('')
  const [source, setSource] = useState('')
  const q = useApi('/api/gap' + qs({ theme_id: themeId, region_id: regionId, lens: filters.lens, week: filters.week, source: source || undefined }))
  const d = q.data
  useEffect(() => dwell('gap', `${themeId}:${regionId}`, { lens: filters.lens }), [themeId, regionId, filters.lens])

  const nm = (o) => (o ? (lang === 'ar' ? o.name_ar : o.name_en) : '')
  // the heading comes from /api/meta, so it is there before the gap loads (focus lands on it at once)
  const theme = meta.themes.find((x) => x.id === themeId)
  const region = meta.regions.find((r) => r.id === regionId)
  const title = `${nm(theme)} · ${nm(region)}`
  usePageTitle(title)
  const lensInfo = LENS_TEXT[filters.lens]
  const lensMeta = meta.lenses.find((l) => l.key === filters.lens)

  const reload = () => { q.retry(); refresh() }
  const vote = useMutation((v) => api('/api/gap/vote', { method: 'POST', body: {
    theme_id: themeId, region_id: regionId, week: d.week, lens: filters.lens, vote: v,
    note: voteNote || null, covered_url: v === 'covered' ? coveredUrl : null } }),
  { onSuccess: () => { setPending(null); setCoveredUrl(''); clearVoteNote(); reload() } })
  const castVote = (v) => {
    if (v === 'covered' && !coveredUrl) { setPending('covered'); return }
    vote.run(v)
  }
  const claim = useMutation((status) => api('/api/gap/claim', { method: 'POST', body: {
    theme_id: themeId, region_id: regionId, status, published_url: status === 'published' ? claimUrl : null } }),
  { onSuccess: reload })

  const here = gapPath(themeId, regionId, { lens: filters.lens, week: filters.week })
  // the weeks judged end on the Sunday of the gap's week (d.week is its Monday; d.window's end is exclusive)
  const subtitle = d
    ? t('{lens} lens · {n} weeks to {date}', { lens: lensInfo.label, n: meta.window_weeks, date: fmtDate(weekEnd(d.week)) })
    : lensInfo?.label
  const c = d?.cell
  const b = c?.breakdown || {}
  // own_history lenses compare with the theme's usual level, pooled ones with what other topics get
  const reference = lensMeta?.reference || b.reference
  const myVote = d?.votes.find((v) => v.mine && v.week === d.week)
  const myClaim = d?.claims.find((x) => x.mine)
  // the server sends at most 150 articles; the full list is the Articles page with the same window
  const shown = d?.articles.items.length ?? 0
  const seeAll = d && articlesPath({ theme_id: themeId, region_id: d.region.level === 'national' ? '' : regionId, start: d.window[0], end: d.window[1], source })

  return (
    <Dialog title={title} subtitle={subtitle} onClose={closePanel} actions={<CopyLink path={here} objectType="gap" objectKey={`${themeId}:${regionId}`} />}>
      {!d && q.error && <ErrorBox error={q.error} onRetry={q.retry} />}
      {!d && !q.error && <Loading />}
      {d && (
        <>
          {q.error && <ErrorBox error={q.error} onRetry={q.retry} compact />}
          {lang !== 'ar' && <div className="small ar" dir="rtl">{d.theme.name_ar} · {d.region.name_ar}</div>}
          <div className="row" style={{ gap: 24, margin: '14px 0' }}>
            <div className="stat"><span className="v num">{fmt(c?.articles_all ?? c?.coverage ?? d.articles.total)}</span><span className="l">{t('monitored articles')}</span></div>
            <div className="stat"><span className="v num">{fmt(c?.need ?? 0)}</span><span className="l">{lensInfo.unit}</span></div>
            <div className="stat"><span className="v" style={{ fontSize: 16, maxWidth: 200 }}>{gapLabel(c && !c.insufficient ? c.gap : null, meta.red_from)}</span>
              <span className="l">{reference === 'own_history' ? t('compared with this theme’s usual level') : t('compared with other topics')}</span></div>
          </div>
          {(!c || c.insufficient) && <p className="small" style={{ marginTop: 0 }}><Link to="/help#not-judged">{t('Why a gap is not judged')}</Link></p>}
          {b.articles_4w != null && b.expected_4w != null && (
            <p className="small muted" style={{ marginTop: 0 }}>{reference === 'pooled'
              ? t('The score counts {count} of these, from the outlets we followed all year, against {expected} expected from other topics.', { count: fmt(b.articles_4w), expected: about(b.expected_4w) })
              : t('The score counts {count} of these, from the outlets we followed all year, against {expected} expected from this theme’s usual level.', { count: fmt(b.articles_4w), expected: about(b.expected_4w) })}</p>)}
          {c?.flags?.length > 0 && <div className="row"><WarningPills codes={c.flags} /></div>}
          {filters.lens === 'search' && <SearchTerms search={d.search} missing={b.search_missing_weeks} />}
          {c && (
            <>
              <h3>{t('Who is covering it')}</h3>
              <MixBar parts={b.scope || {}} labels={DIMENSIONS.scope.values}
                colors={{ libyan: 'var(--scope-libyan)', international: 'var(--scope-international)', diaspora: 'var(--scope-diaspora)' }} />
              <div style={{ height: 8 }} />
              <MixBar parts={b.lang || {}} labels={{ ar: t('Arabic'), en: t('English'), und: t('Unknown') }}
                colors={{ ar: 'var(--scope-libyan)', en: 'var(--scope-international)' }} />
              <BlindSpots compact />
              <p className="small muted">{t('Previous 4 weeks: {articles} articles vs {need} {unit}. Monitored sources only.', { articles: fmt(b.prev_coverage), need: fmt(b.prev_need), unit: lensInfo.unit })}</p>
            </>)}

          <div className="row" style={{ justifyContent: 'space-between' }}>
            <h3>{t('What’s been written ({n})', { n: fmt(d.articles.total) })}</h3>
            {can && <button className="btn small" onClick={() => openAdd({ theme_ids: [themeId], region_ids: d.region.level === 'national' ? [] : [regionId] })}>{t('+ Add missing article')}</button>}
          </div>
          <SourceFilter counts={d.articles.by_source} value={source} onChange={setSource} />
          {d.articles.items.length === 0 && <p className="small muted">{t('No monitored article in this period.')}</p>}
          <ul className="list">{d.articles.items.map((it) => <ArticleRow key={it.id} item={it} onChanged={q.retry} context={{ themeId, regionId, from: 'gap' }} />)}</ul>
          {shown < d.articles.total && (
            <p className="small"><Link to={seeAll}>{t('Showing {shown} of {total} · see all', { shown: fmt(shown), total: fmt(d.articles.total) })}</Link></p>)}

          <h3>{t('Is this a real gap?')}</h3>
          {can && (
            <>
              <div className="row">
                {VOTES.map(([k, label, hint]) => (
                  <button key={k} className="btn" aria-pressed={myVote?.vote === k} title={t(hint)} disabled={vote.busy} onClick={() => castVote(k)}>{t(label)}</button>))}
              </div>
              {pending === 'covered' && (
                <div className="row" style={{ marginTop: 8 }}>
                  <input type="url" placeholder={t('https://… link to the coverage')} value={coveredUrl} onChange={(e) => setCoveredUrl(e.target.value)} style={{ flex: 1 }} aria-label={t('Coverage link')} />
                  <button className="btn primary" disabled={!coveredUrl || vote.busy} onClick={() => vote.run('covered')}>{t('Save')}</button>
                </div>)}
              <textarea style={{ marginTop: 8 }} dir="auto" placeholder={t('Optional: why? (stored with your vote)')} value={voteNote} onChange={(e) => setVoteNote(e.target.value)} aria-label={t('Vote note')} />
              {vote.error && <ErrorBox error={vote.error} compact />}
            </>)}
          {d.votes.length > 0 && <ul className="list small">{d.votes.slice(0, 8).map((v, i) =>
            <li key={i}><b dir="auto">{v.user}</b> · {VOTE_CODE[v.vote] ? t(VOTE_CODE[v.vote]) : v.vote.replace('_', ' ')} <span className="muted">({v.week ? weekRange(v.week) : ''})</span>{v.note && <div dir="auto">{v.note}</div>}</li>)}</ul>}
          {!can && d.votes.length === 0 && <p className="small muted">{t('No votes yet.')}</p>}

          <h3>{t('Working on it')}</h3>
          {can && (
            <div className="row">
              <button className="btn" aria-pressed={myClaim?.status === 'working'} disabled={claim.busy} onClick={() => claim.run('working')}>{t('I’m working on this')}</button>
              <input type="url" placeholder={t('Published link')} value={claimUrl} onChange={(e) => setClaimUrl(e.target.value)} aria-label={t('Published link')} />
              <button className="btn" disabled={!claimUrl || claim.busy} onClick={() => claim.run('published')}>{t('Mark published')}</button>
              {myClaim && <button className="btn ghost small" disabled={claim.busy} onClick={() => claim.run('dropped')}>{t('Drop')}</button>}
            </div>)}
          {claim.error && <ErrorBox error={claim.error} compact />}
          {d.claims.filter((x) => x.status !== 'dropped').map((x, i) => <div key={i} className="small muted"><span dir="auto">{x.user}</span>: {CLAIM_STATUS[x.status] ? t(CLAIM_STATUS[x.status]) : x.status}{x.published_url && <> · <a href={x.published_url} target="_blank" rel="noreferrer noopener">{t('link')}</a></>}</div>)}
          {!can && !d.claims.some((x) => x.status !== 'dropped') && <p className="small muted">{t('Nobody has claimed this yet.')}</p>}
          <p className="small muted">{t('Visible to your team only.')}</p>

          <h3>{t('Discussion')}</h3>
          <Comments objectType="gap" objectKey={d.object_key} />

          {d.statements?.total > 0 && (
            <>
              <h3>{t('Official statements ({n})', { n: fmt(d.statements.total) })}</h3>
              <p className="small muted">{t('UN, embassy and government statements on this theme in the same weeks. Not counted as coverage.')}</p>
              <ul className="list small">{d.statements.items.slice(0, 15).map((it) => (
                <li key={it.id}>{fmtDate(it.published_at)} · <a href={it.url} target="_blank" rel="noreferrer noopener" dir="auto">{it.title}</a> <span className="muted">· <span dir="auto">{it.outlet?.name}</span></span></li>))}</ul>
            </>)}
          {d.need_items.total > 0 && (
            <>
              <h3>{t('Need signals ({n})', { n: fmt(d.need_items.total) })}</h3>
              <ul className="list small">{d.need_items.items.slice(0, 20).map((it) => <li key={it.id}>{fmtDate(it.published_at)} · <span dir="auto">{it.title}</span> <span className="muted num">{fmt(it.value)}</span></li>)}</ul>
            </>)}
          <p className="small muted" style={{ marginTop: 16 }}>{t('Gap = how much less coverage there is than expected, given the need signal. A gap is not judged when there is too little need data, or when we would expect fewer than {n} articles.', { n: lensMeta?.min_expected ?? 3 })} <Link to="/help#gap">{t('More in Help')}</Link></p>
        </>)}
    </Dialog>
  )
}
