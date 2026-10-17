import { useEffect, useState } from 'react'
import { api, dwell, qs } from '../api'
import { useApp } from '../App'
import { MixBar } from '../charts/Balance'
import { INFO_FLAGS, DIMENSIONS, LENS_TEXT, flagText, fmt, gapLabel } from '../charts/scales'
import { about } from '../charts/trendText'
import { fmtDate, isAr, t } from '../i18n'
import Comments from './Comments'
import ArticleRow from './ArticleRow'
import BlindSpots from './BlindSpots'
import SourceFilter from './SourceFilter'
import SearchTerms from './SearchTerms'

const N_ = (s) => s // marks English for the catalogue; translated with t() when shown

const VOTES = [
  ['real', N_('Real gap'), N_('This is under-reported and worth covering')],
  ['covered', N_('Already covered'), N_('Paste the link — it will count as coverage')],
  ['not_newsworthy', N_('Not newsworthy'), N_('The signal is real but not a story')],
]
// vote and claim codes from the API, shown as they read in English
const VOTE_CODE = { real: N_('real'), covered: N_('covered'), not_newsworthy: N_('not newsworthy') }
const CLAIM_STATUS = { working: N_('working'), published: N_('published'), dropped: N_('dropped') }
// ISO dates stay as they are in English; Arabic gets Libyan month names
const day = (s) => (isAr() && s ? fmtDate(s) : s)

export default function GapPanel({ themeId, regionId, week: weekProp, lens: lensProp }) {
  const { meta, filters: f0, lang, closePanel, refresh, openAdd } = useApp()
  // a chart can open the panel at a given week/lens without changing the page-wide filters
  const filters = { ...f0, lens: lensProp || f0.lens, week: weekProp || f0.week }
  const [d, setD] = useState(null)
  const [voteNote, setVoteNote] = useState('')
  const [coveredUrl, setCoveredUrl] = useState('')
  const [pending, setPending] = useState(null)
  const [err, setErr] = useState(null)
  const [claimUrl, setClaimUrl] = useState('')
  const [source, setSource] = useState('')
  const load = () => api('/api/gap' + qs({ theme_id: themeId, region_id: regionId, lens: filters.lens, week: filters.week, source: source || undefined })).then(setD)
  useEffect(() => { load() }, [themeId, regionId, filters.lens, filters.week, source])
  useEffect(() => dwell('gap', `${themeId}:${regionId}`, { lens: filters.lens }), [themeId, regionId, filters.lens])

  if (!d) return <aside className="drawer" aria-label={t('Gap detail')}><div className="empty">{t('Loading…')}</div></aside>
  const c = d.cell
  const lensInfo = LENS_TEXT[filters.lens]
  const lensMeta = meta.lenses.find((l) => l.key === filters.lens)
  const myVote = d.votes.find((v) => v.mine && v.week === d.week)
  const myClaim = d.claims.find((x) => x.mine)
  const vote = async (v) => {
    if (v === 'covered' && !coveredUrl) { setPending('covered'); return }
    try {
      await api('/api/gap/vote', { method: 'POST', body: { theme_id: themeId, region_id: regionId, week: d.week, lens: filters.lens, vote: v, note: voteNote || null, covered_url: v === 'covered' ? coveredUrl : null } })
      setPending(null); setCoveredUrl(''); setErr(null); load(); refresh()
    } catch (e) { setErr(e.message) }
  }
  const claim = async (status) => {
    try {
      await api('/api/gap/claim', { method: 'POST', body: { theme_id: themeId, region_id: regionId, status, published_url: status === 'published' ? claimUrl : null } })
      setErr(null); load(); refresh()
    } catch (e) { setErr(e.message) }
  }
  const nm = (o) => (lang === 'ar' ? o.name_ar : o.name_en)
  const b = c?.breakdown || {}
  // own_history lenses compare with the theme's usual level, pooled ones with what other topics get
  const reference = lensMeta?.reference || b.reference
  return (
    <aside className="drawer" aria-label={t('Gap detail')}>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <div>
          <div className="small muted">{t('{lens} lens · window {from} → {to}', { lens: lensInfo.label, from: day(d.window[0]), to: day(d.window[1]) })}</div>
          <h2 style={{ margin: '2px 0' }}>{nm(d.theme)} · {nm(d.region)}</h2>
          {lang !== 'ar' && <div className="small ar" dir="rtl">{d.theme.name_ar} · {d.region.name_ar}</div>}
        </div>
        <button className="btn ghost" onClick={closePanel} aria-label={t('Close')}>✕</button>
      </div>

      <div className="row" style={{ gap: 24, margin: '14px 0' }}>
        <div className="stat"><span className="v num">{fmt(c?.coverage ?? d.articles.total)}</span><span className="l">{t('monitored articles')}</span></div>
        <div className="stat"><span className="v num">{fmt(c?.need ?? 0)}</span><span className="l">{lensInfo.unit}</span></div>
        <div className="stat"><span className="v" style={{ fontSize: 16, maxWidth: 200 }}>{c ? gapLabel(c.insufficient ? null : c.gap) : t('not scored')}</span>
          <span className="l">{reference === 'own_history' ? t('vs this theme’s previous 12 weeks') : t('vs comparable cells')}</span></div>
      </div>
      {b.articles_4w != null && b.expected_4w != null && (
        <p className="small muted" style={{ marginTop: 0 }}>{reference === 'pooled'
          ? t('The score counts {count} of these, from the outlets we followed through the whole comparison, against {expected} expected.', { count: fmt(b.articles_4w), expected: about(b.expected_4w) })
          : t('The score counts {count} of these, from the outlets we followed through the whole comparison, against {expected} usual.', { count: fmt(b.articles_4w), expected: about(b.expected_4w) })}</p>)}
      {c?.flags?.length > 0 && <div className="row">{c.flags.map((f) => <span key={f} className={INFO_FLAGS.has(f) ? "pill" : "pill flag"}>{flagText(f)}</span>)}</div>}
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

      <h3>{t('Is this a real gap?')}</h3>
      <div className="row">
        {VOTES.map(([k, label, hint]) => (
          <button key={k} className="btn" aria-pressed={myVote?.vote === k} title={t(hint)} onClick={() => vote(k)}>{t(label)}</button>))}
      </div>
      {pending === 'covered' && (
        <div className="row" style={{ marginTop: 8 }}>
          <input type="url" placeholder={t('https://… link to the coverage')} value={coveredUrl} onChange={(e) => setCoveredUrl(e.target.value)} style={{ flex: 1 }} aria-label={t('Coverage link')} />
          <button className="btn primary" disabled={!coveredUrl} onClick={() => vote('covered')}>{t('Save')}</button>
        </div>)}
      <textarea style={{ marginTop: 8 }} dir="auto" placeholder={t('Optional: why? (stored with your vote)')} value={voteNote} onChange={(e) => setVoteNote(e.target.value)} aria-label={t('Vote note')} />
      {d.votes.length > 0 && <ul className="list small">{d.votes.slice(0, 8).map((v, i) =>
        <li key={i}><b dir="auto">{v.user}</b> · {VOTE_CODE[v.vote] ? t(VOTE_CODE[v.vote]) : v.vote.replace('_', ' ')} <span className="muted">({day(v.week)})</span>{v.note && <div dir="auto">{v.note}</div>}</li>)}</ul>}

      <h3>{t('Working on it')}</h3>
      <div className="row">
        <button className="btn" aria-pressed={myClaim?.status === 'working'} onClick={() => claim('working')}>{t('I’m working on this')}</button>
        <input type="url" placeholder={t('Published link')} value={claimUrl} onChange={(e) => setClaimUrl(e.target.value)} aria-label={t('Published link')} />
        <button className="btn" disabled={!claimUrl} onClick={() => claim('published')}>{t('Mark published')}</button>
        {myClaim && <button className="btn ghost small" onClick={() => claim('dropped')}>{t('Drop')}</button>}
      </div>
      {d.claims.filter((x) => x.status !== 'dropped').map((x, i) => <div key={i} className="small muted"><span dir="auto">{x.user}</span>: {CLAIM_STATUS[x.status] ? t(CLAIM_STATUS[x.status]) : x.status}{x.published_url && <> · <a href={x.published_url} target="_blank" rel="noreferrer noopener">{t('link')}</a></>}</div>)}
      <p className="small muted">{t('Visible to your team only.')}</p>
      {err && <p className="err">{err}</p>}

      <h3>{t('Discussion')}</h3>
      <Comments objectType="gap" objectKey={d.object_key} />

      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h3>{t('Articles in window ({n})', { n: fmt(d.articles.total) })}</h3>
        <button className="btn small" onClick={() => openAdd({ theme_ids: [themeId], region_ids: d.region.level === 'national' ? [] : [regionId] })}>{t('+ Add missing article')}</button>
      </div>
      <SourceFilter counts={d.articles.by_source} value={source} onChange={setSource} />
      <ul className="list">{d.articles.items.map((it) => <ArticleRow key={it.id} item={it} onChanged={load} context={{ themeId, regionId }} />)}</ul>
      {d.statements?.total > 0 && (
        <>
          <h3>{t('Official statements ({n})', { n: fmt(d.statements.total) })}</h3>
          <p className="small muted">{t('UN, embassy and government statements on this theme in the window. Not counted as coverage.')}</p>
          <ul className="list small">{d.statements.items.slice(0, 15).map((it) => (
            <li key={it.id}>{day(it.published_at.slice(0, 10))} · <a href={it.url} target="_blank" rel="noreferrer noopener" dir="auto">{it.title}</a> <span className="muted">· <span dir="auto">{it.outlet?.name}</span></span></li>))}</ul>
        </>)}
      {d.need_items.total > 0 && (
        <>
          <h3>{t('Need signals ({n})', { n: fmt(d.need_items.total) })}</h3>
          <ul className="list small">{d.need_items.items.slice(0, 20).map((it) => <li key={it.id}>{day(it.published_at.slice(0, 10))} · <span dir="auto">{it.title}</span> <span className="muted num">{fmt(it.value)}</span></li>)}</ul>
        </>)}
      <p className="small muted" style={{ marginTop: 16 }}>{t('Gap = how much less coverage there is than expected given the need signal. Small cells are pulled towards the expected number. A cell is not scored when there is too little need data or we would expect fewer than {n} articles.', { n: lensMeta?.min_expected ?? 3 })}</p>
    </aside>
  )
}
