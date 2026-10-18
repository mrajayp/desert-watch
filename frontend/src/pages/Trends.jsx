import { useCallback, useMemo, useRef, useState } from 'react'
import { qs } from '../api'
import { useApp } from '../App'
import Filters from '../components/Filters'
import { ErrorBox, Loading } from '../components/Notices'
import TrendBars from '../charts/TrendBars'
import Heatmap from '../charts/Heatmap'
import IndicatorLines from '../charts/IndicatorLines'
import { lensNeed, weekEnd, weekRange } from '../charts/trendText'
import { HistoryLine, LanguageBalance, MonthlyCoverage } from '../charts/Balance'
import { LENS_TEXT, RED_FROM, sourceLabel } from '../charts/scales'
import { ExportMenu } from '../charts/util'
import { useApi } from '../hooks/useApi'
import { usePageTitle } from '../hooks/usePageTitle'
import { fmtDate, fmtMonth, isAr, pick, t } from '../i18n.js'

// marks a string for the Arabic catalogue where a table is defined; t() translates it when it is shown
const N_ = (s) => s
const longDate = (s) => fmtDate(s)
const andList = (xs) => (xs.length < 2 ? xs.join('') : t('{list} and {last}', { list: xs.slice(0, -1).join(isAr() ? '، ' : ', '), last: xs[xs.length - 1] }))
// source names as they read mid-sentence (the labels elsewhere are capitalised)
const BASIS_WORDS = { rss: N_('outlet feeds'), galerts: N_('Google Alerts'), gnews: N_('Google News'), gdelt: 'GDELT', youtube: N_('YouTube channels'),
  gnews_social: N_('social posts found through Google'), official: N_('official statements'), user: N_('links added by the team') }
const basisWord = (k) => (BASIS_WORDS[k] ? t(BASIS_WORDS[k]) : sourceLabel(k))
// "from A to B" for the article lists opened from a day (ISO days in, written dates out)
const daySpan = (from, to) => t('{from} → {to}', { from: fmtDate(from), to: fmtDate(to) })

export default function Trends() {
  const { meta, filters, setFilters, lang, openGap, openArticles, version } = useApp()
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
  usePageTitle(t('Trends'))
  const histSvg = useRef(null)
  // By region: the gap heatmap and the language balance for the lens and week in the URL
  const heatSvg = useRef(null), langSvg = useRef(null)
  const red = meta.red_from ?? RED_FROM
  const nationalOnly = lensMeta && lensMeta.levels.length === 1
  const cellsQ = useApi(filters.week ? '/api/cells' + qs({ lens: filters.lens, week: filters.week }) : null, { deps: [version] })
  const cells = cellsQ.data?.cells || []
  // a national-only lens still has regional article counts worth showing (unscored, striped)
  const ctxQ = useApi(nationalOnly && filters.week ? '/api/cells' + qs({ lens: 'journalist', week: filters.week }) : null, { deps: [version] })
  const regionalContext = useMemo(() => (nationalOnly && ctxQ.data
    ? ctxQ.data.cells.filter((c) => meta.regions.find((r) => r.id === c.region_id)?.level !== 'national').map((c) => ({ ...c, insufficient: true, gap: null, flags: [] }))
    : []), [ctxQ.data, nationalOnly, meta])
  const nationalCells = cells.filter((c) => c.region_id === national.id)
  const heatRegions = [national, ...meta.regions.filter((r) => r.level === 'macro')]
  const feedback = Object.fromEntries(cells.map((c) => [`${c.theme_id}:${c.region_id}`, c.votes]))
  // the weeks shown end on the Sunday of the selected week (filters.week is its Monday)
  const weekDate = filters.week ? fmtDate(weekEnd(filters.week)) : ''
  const cellsCaption = t('Source: Desert Watch monitored coverage (Google News, Google Alerts, GDELT, outlet and YouTube feeds, social posts Google indexes) · {window}.',
    { window: t('{n} weeks to {date}', { n: meta.window_weeks, date: weekDate }) })
  const grp = String(filters.themeId).startsWith('group:') ? filters.themeId.slice(6) : null
  const themeId = grp ? meta.themes.find((t) => t.group === grp)?.id : filters.themeId ? +filters.themeId : meta.themes[0].id
  const monthSvg = useRef(null)
  const monthlyQ = useApi('/api/coverage-monthly' + qs({ theme_id: themeId }))
  const monthly = monthlyQ.data || []
  const trendQ = useApi('/api/cells/trends' + qs({ lens: filters.lens, region_id: regionId }))
  // the bars for one lens and region: shown only once that answer is in (never the previous lens's bars)
  const trend = trendQ.refreshing ? null : trendQ.data
  const historyQ = useApi('/api/coverage-history' + qs({ theme_id: themeId }))
  const history = historyQ.data || {}
  const theme = meta.themes.find((t) => t.id === themeId)
  const [signalDays, setSignalDays] = useState(400)
  const signalsQ = useApi('/api/indicators' + qs({ theme: 'economy', days: signalDays }))
  const signals = signalsQ.data || (signalsQ.error ? { indicators: [] } : null)
  const loadError = monthlyQ.error || historyQ.error
  const retryLoads = () => { monthlyQ.retry(); historyQ.retry() }
  const economy = meta.themes.find((t) => t.slug === 'economy')
  const pickSignalDay = (day) => {
    if (!economy) return
    const end = new Date(day + 'T00:00:00Z'), start = new Date(end.getTime() - 6 * 864e5)
    openArticles({ title: `${tname(economy)} · ${daySpan(iso(start), day)}`, subtitle: t('Economy articles for the 7 days to this day'),
      query: { theme_id: economy.id, start: iso(start), end: day } })
  }
  const tname = (th) => (lang === 'ar' ? th.name_ar : th.name_en)
  const iso = (d) => d.toISOString().slice(0, 10)
  const country = pick(meta.country, 'name')
  const where = region.level === 'national' ? t('All of {country}', { country }) : pick(region, 'name')
  const pickTheme = useCallback((id) => setFilters({ themeId: String(id) }), [setFilters])
  const pickWeek = useCallback((tid, week) => openGap(tid, regionId, { week, lens: filters.lens, from: 'trends' }), [openGap, regionId, filters.lens])
  const pickBar = useCallback((th, r) => openArticles({
    title: `${lang === 'ar' ? th.name_ar : th.name_en} · ${weekRange(r.week)}`, subtitle: t('{where}. The articles counted in this bar.', { where }),
    note: t('These come from the outlets we followed all year, so the list adds up to the bar. Switch to all sources to see every article we have for that week.'),
    query: { theme_id: th.id, region_id: regionId, start: r.week, end: weekEnd(r.week), basis: 'trend' } }), [openArticles, regionId, where, lang])
  const pickMonth = (m) => {
    const first = new Date(m + '-01T00:00:00Z')
    const last = new Date(Date.UTC(first.getUTCFullYear(), first.getUTCMonth() + 1, 0))
    openArticles({ title: `${tname(theme)} · ${fmtMonth(m)}`, subtitle: t('All of Libya, by publication date'),
      note: t('These are the articles counted in this bar. Use Correct on any row that does not belong; the chart updates after the next recalculation.'),
      query: { theme_id: themeId, start: iso(first), end: iso(last) } })
  }
  const pickDay = (day) => {
    const end = new Date(day + 'T00:00:00Z')
    const start = new Date(end.getTime() - 6 * 864e5)
    openArticles({ title: `${tname(theme)} · ${daySpan(iso(start), day)}`, subtitle: t('Desert Watch articles for the same 7 days'),
      note: t('The line counts articles in GDELT’s worldwide index, which does not hand out the list. These are the articles Desert Watch collected for the same seven days, as the nearest reviewable sample.'),
      query: { theme_id: themeId, start: iso(start), end: day } })
  }
  const basis = trend?.basis
  return (
    <>
      <Filters showColor={false} showTheme={false}>
        <label>{t('Region')}
          <select value={regionId} onChange={(e) => setRegionPick(+e.target.value)} disabled={regions.length < 2}
            title={regions.length < 2 ? t('The {lens} lens only has figures for all of {country}', { lens: LENS_TEXT[filters.lens]?.label || filters.lens, country }) : undefined}>
            {regions.filter((r) => r.level !== 'district').map((r) => <option key={r.id} value={r.id}>{r.level === 'macro' ? '· ' : ''}{pick(r, 'name')}</option>)}
            {regions.some((r) => r.level === 'district') && (
              <optgroup label={t('Districts')}>{regions.filter((r) => r.level === 'district').map((r) => <option key={r.id} value={r.id}>{pick(r, 'name')}</option>)}</optgroup>)}
          </select>
        </label>
      </Filters>
      <main className="page">
        {loadError && <ErrorBox error={loadError} onRetry={retryLoads} />}
        <section className="card">
          <h2>{t('Articles per week, theme by theme')}</h2>
          <p className="sub">{t('Bars count the articles each week from the outlets we followed all year.')} {pooled
            ? t('The grey line is the expected level for {what}, going by what other topics get.', { what: t(need.usual) })
            : t('The grey line is the expected level for {what}, going by this theme’s own record.', { what: t(need.usual) })} {t('The strip under each chart turns red when the last 4 weeks fell clearly short. Google News finds more for recent weeks when we search back, so bars run higher on the right.')}{pooled ? '' : ` ${t('The expected level lags behind that rise, so recent weeks can look better covered than they were.')}`} {t('Click a bar to see its articles, or the strip under it for the full gap. A theme’s name picks it for the charts below.')}</p>
          {!trend ? (trendQ.error && !trendQ.refreshing ? <ErrorBox error={trendQ.error} onRetry={trendQ.retry} /> : <Loading />) : (
            <>
              <TrendBars themes={meta.themes} data={trend} lens={filters.lens} reference={lensMeta?.reference}
                scoredWeek={filters.lens === 'search' ? lensMeta?.latest_scored_week : null} lang={lang} selectedId={themeId}
                onSelect={pickTheme} onPickWeek={pickWeek} onPickBar={pickBar} />
              {basis && basis.outlets > 0 && (
                <p className="small muted" style={{ margin: '8px 0 0' }}>
                  {t('The counts cover the {outlets} outlets we collected from all through {from} to {to}, from {sources}. We leave out the backfill and newer feeds so a new source does not look like more coverage.',
                    { outlets: basis.outlets, from: longDate(basis.from), to: longDate(basis.to), sources: andList(basis.sources.map(basisWord)) })}</p>)}
            </>)}
        </section>
        <section className="card" style={{ marginTop: 16 }}>
          <div className="card-head">
            <div><h2>{t('By region')}</h2>
              <p className="sub">{t('{lens} lens · {n} weeks to {date}', { lens: t(LENS_TEXT[filters.lens].label), n: meta.window_weeks, date: weekDate })}. {nationalOnly
                ? t('Striped = not judged: the week is still coming in, or there is too little data. This lens is national only, so the regional columns show article counts until regional need data arrives.')
                : t('Striped = not judged: the week is still coming in, or there is too little data.')}</p></div>
            <ExportMenu svgRef={heatSvg} title={t('Coverage gaps by theme and region — {country}', { country })} caption={cellsCaption} filename="gap-heatmap" />
          </div>
          {cellsQ.error && <ErrorBox error={cellsQ.error} onRetry={cellsQ.retry} compact />}
          <Heatmap themes={meta.themes} regions={heatRegions} cells={[...cells, ...regionalContext]} svgRef={heatSvg} unit={LENS_TEXT[filters.lens].unit} lang={lang}
            feedback={feedback} red={red} onSelect={(tid, rid) => openGap(tid, rid, { from: 'heatmap' })} />
          <div className="card-head" style={{ marginTop: 18 }}>
            <div><h3 style={{ margin: 0 }}>{t('Arabic vs English coverage')}</h3>
              <p className="sub">{t('Monitored articles nationally, {n} weeks ending {week}.', { n: meta.window_weeks, week: weekDate })}</p></div>
            <ExportMenu svgRef={langSvg} title={t('Arabic vs English coverage of {country}', { country })} caption={cellsCaption} filename="language-balance" />
          </div>
          <LanguageBalance themes={meta.themes} cells={nationalCells} lang={lang} svgRef={langSvg} />
        </section>
        {signals?.indicators?.length > 0 && (
          <section className="card" style={{ marginTop: 16 }}>
            <div className="card-head">
              <h2>{t('Economy signals from outside the news')}</h2>
              <span className="seg" role="group" aria-label={t('Range')}>
                {[[400, t('Last year')], [4000, t('Since 2016')]].map(([d, l]) =>
                  <button key={d} aria-pressed={signalDays === d} onClick={() => setSignalDays(d)}>{l}</button>)}</span>
            </div>
            <p className="sub">{t('Daily numbers that show what people in Libya are dealing with, next to what the outlets write. Each line has its own scale and is never scored. Click a day to see that week\'s economy articles.')}</p>
            <IndicatorLines indicators={signals.indicators} charts={signals.charts} onPickDay={pickSignalDay} />
          </section>)}
        <section className="card" style={{ marginTop: 16 }}>
          <div className="card-head">
            <div><h2>{t('Collected coverage by month')} · {lang === 'ar' ? theme.name_ar : theme.name_en}</h2>
              <p className="sub">{t('Relevant articles we collected for this theme each month, coloured by how they reached us. Google News reaches older months through a search by date range. The backfill holds the links cited in the UNSMIL review. The current month is hatched because it is not over yet. Circles mark dated events. Click a bar to list its articles.')}</p></div>
            <div className="row">
              <select value={themeId} onChange={(e) => setFilters({ themeId: e.target.value })} aria-label={t('Theme')}>
                {meta.themes.map((th) => <option key={th.id} value={th.id}>{pick(th, 'name')}</option>)}</select>
              <ExportMenu svgRef={monthSvg} title={t('{theme}: collected coverage of {country} by month', { theme: pick(theme, 'name'), country })} filename="coverage-monthly"
                caption={t('Source: Desert Watch collected coverage (Google News date-range search, outlet RSS, Google Alerts, links cited in the UNSMIL review). Older months are under-represented by search.\nEvents: see docs/research. Compiled by Desert Watch.')} />
            </div>
          </div>
          <MonthlyCoverage rows={monthly} svgRef={monthSvg} onPick={pickMonth}
            markers={(meta.events || []).filter((e) => !e.theme || e.theme === theme.slug)} />
        </section>
        <section className="card" style={{ marginTop: 16 }}>
          <div className="card-head">
            <div><h2>{t('Long-run coverage')} · {lang === 'ar' ? theme.name_ar : theme.name_en}</h2>
              <p className="sub">{t('Daily articles worldwide matching this theme with “{query}” (GDELT, English machine translation of 65 languages). Each point averages the days we have among the 7 calendar days ending there. The line breaks on days GDELT did not give us. Click to review our own articles for that week.', { query: meta.country.name_en })}</p></div>
            <div className="row">
              <select value={themeId} onChange={(e) => setFilters({ themeId: e.target.value })} aria-label={t('Theme')}>
                {meta.themes.map((th) => <option key={th.id} value={th.id}>{pick(th, 'name')}</option>)}</select>
              <ExportMenu svgRef={histSvg} title={t('{theme} coverage of {country}, daily', { theme: pick(theme, 'name'), country })} filename="coverage-history"
                caption={t('Source: GDELT DOC 2.0 API (timelinevolraw), 7-day mean over calendar days. Searches English machine translations.\nCompiled by Desert Watch.')} />
            </div>
          </div>
          <HistoryLine data={history} svgRef={histSvg} onPick={pickDay}
            markers={(meta.events || []).filter((e) => !e.theme || e.theme === theme.slug).map((e) => ({ date: e.date, label: pick(e, 'label') }))} />
        </section>
      </main>
    </>
  )
}
