import { useCallback, useEffect, useRef, useState } from 'react'
import { api, qs } from '../api'
import { useApp } from '../App'
import Filters from '../components/Filters'
import TrendBars from '../charts/TrendBars'
import { lensNeed, weekEnd, weekRange } from '../charts/trendText'
import { HistoryLine, MonthlyCoverage } from '../charts/Balance'
import { LENS_TEXT, sourceLabel } from '../charts/scales'
import { ExportMenu } from '../charts/util'

const longDate = (s) => new Date(s + 'T00:00:00Z').toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' })
const andList = (xs) => (xs.length < 2 ? xs.join('') : `${xs.slice(0, -1).join(', ')} and ${xs[xs.length - 1]}`)
// source names as they read mid-sentence (the labels elsewhere are capitalised)
const BASIS_WORDS = { rss: 'outlet feeds', galerts: 'Google Alerts', gnews: 'Google News', gdelt: 'GDELT', youtube: 'YouTube channels',
  gnews_social: 'social posts found through Google', official: 'official statements', user: 'links added by the team' }
const basisWord = (k) => BASIS_WORDS[k] || sourceLabel(k)

export default function Trends() {
  const { meta, filters, setFilters, lang, openGap, openArticles } = useApp()
  const national = meta.regions.find((r) => r.level === 'national')
  const [regionPick, setRegionPick] = useState(national.id)
  // only regions the lens has need data for (the audience lens is national only)
  const lensMeta = meta.lenses.find((l) => l.key === filters.lens)
  const levels = lensMeta?.levels || ['national']
  const pooled = lensMeta?.reference === 'pooled'
  const need = lensNeed(filters.lens, lensMeta?.reference)
  const regions = meta.regions.filter((r) => levels.includes(r.level))
  const regionId = regions.some((r) => r.id === regionPick) ? regionPick : national.id
  const region = meta.regions.find((r) => r.id === regionId)
  const [trend, setTrend] = useState(null)
  const [history, setHistory] = useState({})
  const histSvg = useRef(null)
  const grp = String(filters.themeId).startsWith('group:') ? filters.themeId.slice(6) : null
  const themeId = grp ? meta.themes.find((t) => t.group === grp)?.id : filters.themeId ? +filters.themeId : meta.themes[0].id
  const [monthly, setMonthly] = useState([])
  const monthSvg = useRef(null)
  useEffect(() => { api('/api/coverage-monthly' + qs({ theme_id: themeId })).then(setMonthly) }, [themeId])
  useEffect(() => {
    let live = true
    setTrend(null)
    api('/api/cells/trends' + qs({ lens: filters.lens, region_id: regionId })).then((r) => live && setTrend(r))
    return () => { live = false }
  }, [filters.lens, regionId])
  useEffect(() => { api('/api/coverage-history' + qs({ theme_id: themeId })).then(setHistory) }, [themeId])
  const theme = meta.themes.find((t) => t.id === themeId)
  const tname = (t) => (lang === 'ar' ? t.name_ar : t.name_en)
  const iso = (d) => d.toISOString().slice(0, 10)
  const where = region.level === 'national' ? `All of ${meta.country.name_en}` : region.name_en
  const pickTheme = useCallback((id) => setFilters({ themeId: String(id) }), [setFilters])
  const pickWeek = useCallback((tid, week) => openGap(tid, regionId, { week, lens: filters.lens, from: 'trends' }), [openGap, regionId, filters.lens])
  const pickBar = useCallback((t, r) => openArticles({
    title: `${lang === 'ar' ? t.name_ar : t.name_en} · ${weekRange(r.week)}`, subtitle: `${where}. The articles counted in this bar.`,
    note: 'These come from the outlets we followed all year, so the list adds up to the bar. Switch to all sources to see every article we have for that week.',
    query: { theme_id: t.id, region_id: regionId, start: r.week, end: weekEnd(r.week), basis: 'trend' } }), [openArticles, regionId, where, lang])
  const pickMonth = (m) => {
    const first = new Date(m + '-01T00:00:00Z')
    const last = new Date(Date.UTC(first.getUTCFullYear(), first.getUTCMonth() + 1, 0))
    openArticles({ title: `${tname(theme)} · ${m}`, subtitle: 'All of Libya, by publication date',
      note: 'These are the articles counted in this bar. Use Fix on any row that does not belong; the chart updates after the next recalculation.',
      query: { theme_id: themeId, start: iso(first), end: iso(last) } })
  }
  const pickDay = (day) => {
    const end = new Date(day + 'T00:00:00Z')
    const start = new Date(end.getTime() - 6 * 864e5)
    openArticles({ title: `${tname(theme)} · ${iso(start)} → ${day}`, subtitle: 'Desert Watch articles for the same 7 days',
      note: 'The line counts articles in GDELT’s worldwide index, which does not hand out the list. These are the articles Desert Watch collected for the same seven days, as the nearest reviewable sample.',
      query: { theme_id: themeId, start: iso(start), end: day } })
  }
  const basis = trend?.basis
  return (
    <>
      <Filters showWeek={false} showColor={false} showTheme={false}>
        <label>Region
          <select value={regionId} onChange={(e) => setRegionPick(+e.target.value)} disabled={regions.length < 2}
            title={regions.length < 2 ? `The ${LENS_TEXT[filters.lens]?.label || filters.lens} lens only has figures for all of ${meta.country.name_en}` : undefined}>
            {regions.filter((r) => r.level !== 'district').map((r) => <option key={r.id} value={r.id}>{r.level === 'macro' ? '· ' : ''}{r.name_en}</option>)}
            {regions.some((r) => r.level === 'district') && (
              <optgroup label="Districts">{regions.filter((r) => r.level === 'district').map((r) => <option key={r.id} value={r.id}>{r.name_en}</option>)}</optgroup>)}
          </select>
        </label>
      </Filters>
      <main className="page">
        <section className="card">
          <h2>Articles per week, theme by theme</h2>
          <p className="sub">Bars count the articles each week from the outlets we followed all year. {pooled
            ? `The grey line is the expected level for ${need.usual}, going by what other topics get.`
            : `The grey line is the usual level for ${need.usual}.`} The strip under each chart turns red when the last 4 weeks fell clearly short. Google News finds more for recent weeks when we search back, so bars run higher on the right.{pooled ? '' : ' The usual level lags behind that rise, so recent weeks can look better covered than they were.'} Click a bar to see its articles, or the strip under it for the full gap. A theme’s name picks it for the charts below.</p>
          {!trend ? <div className="empty">Loading…</div> : (
            <>
              <TrendBars themes={meta.themes} data={trend} lens={filters.lens} reference={lensMeta?.reference}
                scoredWeek={filters.lens === 'search' ? lensMeta?.latest_scored_week : null} lang={lang} selectedId={themeId}
                onSelect={pickTheme} onPickWeek={pickWeek} onPickBar={pickBar} />
              {basis && basis.outlets > 0 && (
                <p className="small muted" style={{ margin: '8px 0 0' }}>
                  The counts cover the {basis.outlets} outlets we collected from all through {longDate(basis.from)} to {longDate(basis.to)}, from {andList(basis.sources.map(basisWord))}. We leave out the backfill and newer feeds so a new source does not look like more coverage.</p>)}
            </>)}
        </section>
        <section className="card" style={{ marginTop: 16 }}>
          <div className="card-head">
            <div><h2>Collected coverage by month · {lang === 'ar' ? theme.name_ar : theme.name_en}</h2>
              <p className="sub">Relevant articles we collected for this theme each month, coloured by how they reached us. Google News reaches older months through a search by date range. The backfill holds the links cited in the UNSMIL review. The current month is hatched because it is not over yet. Circles mark dated events. Click a bar to list its articles.</p></div>
            <div className="row">
              <select value={themeId} onChange={(e) => setFilters({ themeId: e.target.value })} aria-label="Theme">
                {meta.themes.map((t) => <option key={t.id} value={t.id}>{t.name_en}</option>)}</select>
              <ExportMenu svgRef={monthSvg} title={`${theme.name_en}: collected coverage of ${meta.country.name_en} by month`} filename="coverage-monthly"
                caption={'Source: Desert Watch collected coverage (Google News date-range search, outlet RSS, Google Alerts, links cited in the UNSMIL review). Older months are under-represented by search.\nEvents: see docs/research. Compiled by Desert Watch.'} />
            </div>
          </div>
          <MonthlyCoverage rows={monthly} svgRef={monthSvg} onPick={pickMonth}
            markers={(meta.events || []).filter((e) => !e.theme || e.theme === theme.slug)} />
        </section>
        <section className="card" style={{ marginTop: 16 }}>
          <div className="card-head">
            <div><h2>Long-run coverage · {lang === 'ar' ? theme.name_ar : theme.name_en}</h2>
              <p className="sub">Daily articles worldwide matching this theme with “{meta.country.name_en}” (GDELT, English machine translation of 65 languages). Each point averages the days we have among the 7 calendar days ending there. The line breaks on days GDELT did not give us. Click to review our own articles for that week.</p></div>
            <div className="row">
              <select value={themeId} onChange={(e) => setFilters({ themeId: e.target.value })} aria-label="Theme">
                {meta.themes.map((t) => <option key={t.id} value={t.id}>{t.name_en}</option>)}</select>
              <ExportMenu svgRef={histSvg} title={`${theme.name_en} coverage of ${meta.country.name_en}, daily`} filename="coverage-history"
                caption={'Source: GDELT DOC 2.0 API (timelinevolraw), 7-day mean over calendar days. Searches English machine translations.\nCompiled by Desert Watch.'} />
            </div>
          </div>
          <HistoryLine data={history} svgRef={histSvg} onPick={pickDay}
            markers={(meta.events || []).filter((e) => !e.theme || e.theme === theme.slug).map((e) => ({ date: e.date, label: e.label }))} />
        </section>
      </main>
    </>
  )
}
