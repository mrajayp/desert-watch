import { useEffect, useRef, useState } from 'react'
import { api, qs } from '../api'
import { useApp } from '../App'
import Filters from '../components/Filters'
import { TrendMultiples } from '../charts/Heatmap'
import { HistoryLine, MonthlyCoverage } from '../charts/Balance'
import { LENS_TEXT } from '../charts/scales'
import { ExportMenu } from '../charts/util'


export default function Trends() {
  const { meta, filters, setFilters, lang, openGap, openArticles } = useApp()
  const [regionId, setRegionId] = useState(meta.regions.find((r) => r.level === 'national').id)
  const [series, setSeries] = useState({})
  const [basis, setBasis] = useState(null)
  const [history, setHistory] = useState({})
  const histSvg = useRef(null)
  const grp = String(filters.themeId).startsWith('group:') ? filters.themeId.slice(6) : null
  const themeId = grp ? meta.themes.find((t) => t.group === grp)?.id : filters.themeId ? +filters.themeId : meta.themes[0].id
  const [monthly, setMonthly] = useState([])
  const monthSvg = useRef(null)
  useEffect(() => { api('/api/coverage-monthly' + qs({ theme_id: themeId })).then(setMonthly) }, [themeId])
  useEffect(() => { api('/api/cells/trends' + qs({ lens: filters.lens, region_id: regionId })).then((r) => { setSeries(r.series); setBasis(r.trend_basis) }) }, [filters.lens, regionId])
  useEffect(() => { api('/api/coverage-history' + qs({ theme_id: themeId })).then(setHistory) }, [themeId])
  const theme = meta.themes.find((t) => t.id === themeId)
  const tname = (t) => (lang === 'ar' ? t.name_ar : t.name_en)
  const iso = (d) => d.toISOString().slice(0, 10)
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
  return (
    <>
      <Filters showWeek={false} showColor={false} showTheme={false}>
        <label>Region
          <select value={regionId} onChange={(e) => setRegionId(+e.target.value)}>
            {meta.regions.filter((r) => r.level !== 'district').map((r) => <option key={r.id} value={r.id}>{r.level === 'macro' ? '— ' : ''}{r.name_en}</option>)}
            <optgroup label="Districts">{meta.regions.filter((r) => r.level === 'district').map((r) => <option key={r.id} value={r.id}>{r.name_en}</option>)}</optgroup>
          </select>
        </label>
      </Filters>
      <main className="page">
        <section className="card">
          <h2>Need vs coverage, theme by theme</h2>
          <p className="sub">{LENS_TEXT[filters.lens].blurb}. When the blue line falls below the grey one, coverage is falling behind need. Click any week to see the articles and need signals behind it.</p>
          <TrendMultiples themes={meta.themes} series={series} basis={basis} lang={lang} unit={LENS_TEXT[filters.lens].unit}
            onSelect={(id) => setFilters({ themeId: String(id) })}
            onPickWeek={(tid, week) => openGap(tid, regionId, { week, lens: filters.lens, from: 'trends' })} />
        </section>
        <section className="card" style={{ marginTop: 16 }}>
          <div className="card-head">
            <div><h2>Collected coverage by month · {lang === 'ar' ? theme.name_ar : theme.name_en}</h2>
              <p className="sub">Relevant articles collected for this theme per month (Google News backfill, outlet feeds, alerts), with dated reference events. Click a bar to list its articles.</p></div>
            <div className="row">
              <select value={themeId} onChange={(e) => setFilters({ themeId: e.target.value })} aria-label="Theme">
                {meta.themes.map((t) => <option key={t.id} value={t.id}>{t.name_en}</option>)}</select>
              <ExportMenu svgRef={monthSvg} title={`${theme.name_en}: collected coverage of ${meta.country.name_en} by month`} filename="coverage-monthly"
                caption={'Source: Desert Watch monitored coverage (Google News date-range search, outlet RSS, Google Alerts). Older months are under-represented by search.\nEvents: see docs/research. Compiled by Desert Watch.'} />
            </div>
          </div>
          <MonthlyCoverage rows={monthly} svgRef={monthSvg} onPick={pickMonth}
            markers={(meta.events || []).filter((e) => !e.theme || e.theme === theme.slug)} />
        </section>
        <section className="card" style={{ marginTop: 16 }}>
          <div className="card-head">
            <div><h2>Long-run coverage · {lang === 'ar' ? theme.name_ar : theme.name_en}</h2>
              <p className="sub">Daily articles worldwide matching this theme with “{meta.country.name_en}” (GDELT, English machine translation of 65 languages), 7-day average. Click to review our own articles for that week.</p></div>
            <div className="row">
              <select value={themeId} onChange={(e) => setFilters({ themeId: e.target.value })} aria-label="Theme">
                {meta.themes.map((t) => <option key={t.id} value={t.id}>{t.name_en}</option>)}</select>
              <ExportMenu svgRef={histSvg} title={`${theme.name_en} coverage of ${meta.country.name_en}, daily`} filename="coverage-history"
                caption={'Source: GDELT DOC 2.0 API (timelinevolraw), 7-day rolling mean. Searches English machine translations.\nCompiled by Desert Watch.'} />
            </div>
          </div>
          <HistoryLine data={history} svgRef={histSvg} onPick={pickDay}
            markers={(meta.events || []).filter((e) => !e.theme || e.theme === theme.slug).map((e) => ({ date: e.date, label: e.label }))} />
        </section>
      </main>
    </>
  )
}
