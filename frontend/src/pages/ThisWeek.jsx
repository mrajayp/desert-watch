import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { qs, track } from '../api'
import { useApp } from '../App'
import { LENS_TEXT, RED_FROM, fmt, gapFill, verdictOf } from '../charts/scales'
import { lensNeed, verdictSentence, weekEnd, weekRange } from '../charts/trendText'
import ArticleRow from '../components/ArticleRow'
import CoverageMap from '../components/CoverageMap'
import LensSheet from '../components/LensSheet'
import { ErrorBox, Loading } from '../components/Notices'
import SourceHealth from '../components/SourceHealth'
import { WarningPills } from '../components/Warnings'
import { useApi } from '../hooks/useApi'
import { useMedia } from '../hooks/useMedia'
import { usePageTitle } from '../hooks/usePageTitle'
import { fmtDate, pick, t } from '../i18n'
import { articlesPath } from '../routes'

// from here the list sits on the left (56%) with the map open beside it; below, the map is a section
// under the list, collapsed until opened
const DESK = '(min-width: 1000px)'
const RECENT_DAYS = 7, RECENT_ROWS = 10

// the first two lines of a digest, without Markdown marks, for the excerpt card
function excerptOf(md) {
  const lines = (md || '').split('\n').map((l) => l.trim()).filter((l) => l && !l.startsWith('#'))
    .map((l) => l.replace(/^[-*]\s+/, '').replace(/\*\*([^*]+)\*\*/g, '$1').replace(/\*([^*]+)\*/g, '$1').replace(/\[([^\]]+)\]\([^)]*\)/g, '$1'))
  return lines.slice(0, 2).join(' ')
}

// The landing page: what to cover this week, and what has been written already. The week and the lens
// are the page's URL filters (?week=&lens=), as on the Map and Trends pages.
export default function ThisWeek() {
  const { meta, filters, setFilters, openGap, version, can } = useApp()
  usePageTitle(t('This week'))
  const desk = useMedia(DESK)
  const [sheet, setSheet] = useState(false)
  const [mapOpen, setMapOpen] = useState(null) // null: open on a desktop, collapsed below
  const showMap = mapOpen ?? desk
  const red = meta.red_from ?? RED_FROM
  const regionsById = useMemo(() => new Map(meta.regions.map((r) => [r.id, r])), [meta])
  const lensInfo = LENS_TEXT[filters.lens]
  const lensMeta = meta.lenses.find((l) => l.key === filters.lens)
  const need = lensNeed(filters.lens, lensMeta?.reference)
  const week = filters.week ? fmtDate(weekEnd(filters.week)) : ''

  const cellsQ = useApi(filters.week ? '/api/cells' + qs({ lens: filters.lens, week: filters.week }) : null, { deps: [version] })
  const cells = cellsQ.data?.cells || []
  // the ranked gaps: the red ones (verdict short: the shortfall is larger than chance would explain, up to 7),
  // else the five least covered; one lower-ranked cell last as "Also worth a look", so the ranking does
  // not only reinforce itself (its impressions carry explore=true)
  const ranked = useMemo(() => {
    const ok = cells.filter((c) => !c.insufficient && c.gap != null && verdictOf(c, red) !== 'unclear').sort((a, b) => b.gap - a.gap)
    let top = ok.filter((c) => verdictOf(c, red) === 'short').slice(0, 7)
    if (!top.length) top = ok.slice(0, 5).map((c) => ({ ...c, fallback: true }))
    const rest = ok.filter((c) => !top.includes(c))
    if (rest.length && top.length >= 3 && !top[0].fallback) {
      const one = rest[Math.floor(Math.random() * rest.length)]
      top.push({ ...one, explore: true })
    }
    return top
  }, [cells, red])
  useEffect(() => {
    ranked.forEach((c, i) => track('impression', 'gap', `${c.theme_id}:${c.region_id}`, { position: i, lens: filters.lens, explore: !!c.explore, list: 'top_gaps' }))
  }, [ranked, filters.lens])
  const fallback = ranked.length > 0 && ranked[0].fallback

  // the latest good digest, two lines of it
  const digestsQ = useApi('/api/digests')
  const latestDigest = digestsQ.data?.find((d) => d.status === 'ok')
  const digestQ = useApi(latestDigest ? `/api/digests/${latestDigest.id}` : null)
  const excerpt = useMemo(() => (digestQ.data?.status === 'ok' ? excerptOf(digestQ.data.content_md) : ''), [digestQ.data])

  // what was written in the last 7 days, newest first
  const recentQ = useApi('/api/items' + qs({ days: RECENT_DAYS, limit: RECENT_ROWS, offset: 0 }))
  const recent = recentQ.data

  const weeks = [...meta.weeks].reverse() // latest first
  const openCard = (c, i) => openGap(c.theme_id, c.region_id, { position: i, explore: !!c.explore, list: 'top_gaps', from: 'this_week' })

  return (
    <main className="page thisweek">
      <div className="row thisweek-top">
        <label className="row">{t('Week')}
          <select value={filters.week || ''} onChange={(e) => setFilters({ week: e.target.value })}>
            {weeks.map((w) => <option key={w} value={w}>{t('Week of {range}', { range: weekRange(w) })}</option>)}
          </select>
        </label>
        <button type="button" className="chip lens-chip" aria-haspopup="dialog" aria-expanded={sheet} onClick={() => setSheet(true)}>
          {t('Lens: {lens}', { lens: lensInfo.label })}</button>
        {sheet && <LensSheet onClose={() => setSheet(false)} />}
      </div>
      <div className={`thisweek-grid${showMap && desk ? ' with-map' : ''}`}>
        <div className="thisweek-list">
          {excerpt && (
            <section className="card digest-excerpt">
              <h2><Link to="/digest">{t('Weekly brief · week of {week}', { week: weekRange(latestDigest.week_start) })}</Link></h2>
              <p className="clamp-2" dir="auto" style={{ margin: '4px 0 0' }}>{excerpt}</p>
            </section>)}
          <section className="card">
            <h2>{t('Stories nobody is covering')}</h2>
            <p className="sub">{fallback ? t('Least covered, {n} weeks to {date}', { n: meta.window_weeks, date: week }) : t('Biggest gaps, {n} weeks to {date}', { n: meta.window_weeks, date: week })} · {can ? t('{blurb}. Click to review, vote and comment.', { blurb: t(lensInfo.blurb) }) : t('{blurb}. Click to review.', { blurb: t(lensInfo.blurb) })}</p>
            {fallback && <p className="small muted">{t('No theme is clearly falling behind its need signal in these weeks; these are the least covered relative to it.')}</p>}
            {cellsQ.error && <ErrorBox error={cellsQ.error} onRetry={cellsQ.retry} />}
            {!cellsQ.data && !cellsQ.error && <Loading />}
            {cellsQ.data && ranked.length === 0 && <div className="empty">{t('Nothing has been judged for this lens and week.')}</div>}
            {ranked.map((c, i) => {
              const th = meta.themes.find((x) => x.id === c.theme_id)
              const r = regionsById.get(c.region_id)
              // articles = the count the score used; articles_all = every source
              const n = c.articles ?? c.coverage
              const all = c.articles_all ?? c.coverage
              return (
                <div key={`${c.theme_id}:${c.region_id}`} className="gapcard" role="button" tabIndex={0}
                  onClick={() => openCard(c, i)}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openCard(c, i) } }}>
                  <div>
                    <div className="t">{pick(th)} · <span style={{ fontWeight: 400 }}>{pick(r)}</span></div>
                    <div className="verdict">{verdictSentence(c, need, red)}</div>
                    <div className="small muted">{t('{articles} articles vs {need} {unit}', { articles: fmt(n), need: fmt(c.need), unit: t(lensInfo.unit) })}
                      {all != null && all !== n && <span> · {t('{n} from all sources', { n: fmt(all) })}</span>}</div>
                    <div className="row" style={{ marginTop: 4 }}>
                      {c.explore && <span className="pill" title={t("Shown to check the ranking isn't only reinforcing itself")}>{t('Also worth a look')}</span>}
                      <WarningPills codes={c.flags} />
                      {c.votes?.real > 0 && <span className="pill">{t('✓ {n} real', { n: c.votes.real })}</span>}
                      {c.votes?.covered > 0 && <span className="pill">{t('{n} covered', { n: c.votes.covered })}</span>}
                      {c.comments > 0 && <span className="pill">💬 {c.comments}</span>}
                      {c.claims?.working > 0 && <span className="pill ok">{t('someone is on it')}</span>}
                    </div>
                  </div>
                  <span className="dot" style={{ width: 14, height: 14, borderRadius: 4, background: gapFill(c, red) || 'var(--surface-2)' }} aria-hidden="true" />
                </div>)
            })}
            {cellsQ.data && ranked.length > 0 && (
              <p className="small muted" style={{ margin: '10px 0 0' }}>{t('Red means the shortfall is larger than chance would explain. Among the red gaps on a page, about 1 in 10 will still be chance.')}</p>)}
          </section>
          <section className="card">
            <h2>{t('Written this week')}</h2>
            <p className="sub">{t('The newest monitored articles of the last 7 days, from every source.')}</p>
            {!recent && recentQ.error && <ErrorBox error={recentQ.error} onRetry={recentQ.retry} />}
            {!recent && !recentQ.error && <Loading />}
            {recent && recent.items.length === 0 && <p className="small muted">{t('No articles in the last 7 days.')}</p>}
            {recent && <ul className="list">{recent.items.map((it) => <ArticleRow key={it.id} item={it} actions={false} context={{ from: 'this_week' }} />)}</ul>}
            {recent && recent.total > 0 && (
              <p className="small" style={{ marginTop: 8 }}><Link to={articlesPath({ days: RECENT_DAYS })}>{t('See all {n} articles', { n: fmt(recent.total) })}</Link></p>)}
          </section>
        </div>
        <section className="card thisweek-map">
          <button type="button" className="disclose" aria-expanded={showMap} onClick={() => setMapOpen(!showMap)}>
            <span className="caret" aria-hidden="true">▸</span><h2>{t('Map: where coverage reaches')}</h2>
          </button>
          {showMap && <div style={{ marginTop: 10 }}><CoverageMap cells={cells} heading={false} /></div>}
        </section>
      </div>
      <SourceHealth compact />
    </main>
  )
}
