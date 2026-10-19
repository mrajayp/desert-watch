// "Who covers where": outlets joined to the districts their articles name, with the districts shaded
// by the worst gap when the lens has district-level need, else by how many articles name them. One
// component for the Map page and for the map section of the This week page. `cells` are the page's
// /api/cells rows for the lens and week in the URL; the network, the boundaries and the outlet strip
// are loaded here. A district click opens the theme that coloured it (cellsByRegion keeps the worst
// cell per district); with no scored cell it opens the district's articles for the same weeks, never
// an unscored gap for theme #1.
import { geoArea, sum as d3sum } from 'd3'
import { useEffect, useMemo, useRef, useState } from 'react'
import { qs } from '../api'
import { useApp } from '../App'
import GeoNetwork, { GeoLegend } from '../charts/GeoNetwork'
import RegionalNetwork from '../charts/RegionalNetwork'
import { DIMENSIONS, LENS_TEXT, RED_FROM, categoryOf, fmt, verdictOf } from '../charts/scales'
import { weekEnd } from '../charts/trendText'
import { ExportMenu } from '../charts/util'
import { useApi } from '../hooks/useApi'
import { fmtDate, pick, t } from '../i18n'
import { ErrorBox } from './Notices'

// the first day of the window that ends with `week` (a Monday), `weeks` weeks long
const windowStart = (week, weeks) => new Date(new Date(`${week}T00:00:00Z`).getTime() - (weeks - 1) * 7 * 864e5).toISOString().slice(0, 10)

let geoCache = null
async function loadGeo(meta) {
  if (geoCache) return geoCache
  const b = meta.country.boundaries
  const [d, m] = await Promise.all([fetch(`/geo/${b.districts_geojson}`).then((r) => r.json()),
    b.macro_geojson ? fetch(`/geo/${b.macro_geojson}`).then((r) => r.json()) : null])
  // d3-geo uses spherical winding: a polygon whose area exceeds a hemisphere is "inside out"
  // (RFC 7946 files wind the other way). Reverse such rings.
  const rewind = (fc) => { fc.features.forEach((f) => {
    if (geoArea(f) <= 2 * Math.PI) return
    const g = f.geometry
    const rev = (poly) => poly.map((ring) => ring.slice().reverse())
    if (g.type === 'Polygon') g.coordinates = rev(g.coordinates)
    else if (g.type === 'MultiPolygon') g.coordinates = g.coordinates.map(rev) }); return fc }
  geoCache = { districts: rewind(d), macro: m ? rewind(m) : null }
  return geoCache
}

// heading: the "Who covers where" title and its sentence (the landing page's section has its own);
// outlets: the strip of the outlets in view under the map (the Map page)
export default function CoverageMap({ cells, heading = true, outlets = false }) {
  const { meta, filters, lang, openGap, openOutlet, openArticles, version } = useApp()
  const [geo, setGeo] = useState(null)
  const [geoErr, setGeoErr] = useState(null)
  const [geoTick, setGeoTick] = useState(0)
  const [selected, setSelected] = useState(null)
  const [minEdge, setMinEdge] = useState(2)
  const [mapView, setMapView] = useState(() => { try { return localStorage.getItem('dw_mapview') || 'region' } catch { return 'region' } })
  const pickView = (v) => { setMapView(v); try { localStorage.setItem('dw_mapview', v) } catch { /* storage blocked */ } }
  const mapSvg = useRef(null)

  useEffect(() => {
    let live = true
    setGeoErr(null)
    loadGeo(meta).then((g) => live && setGeo(g)).catch((e) => live && setGeoErr(e))
    return () => { live = false }
  }, [meta, geoTick])
  const regionsById = useMemo(() => new Map(meta.regions.map((r) => [r.id, r])), [meta])
  // one red threshold on every page: the API's (settings.GAP_RED_FROM), the same one Trends uses
  const red = meta.red_from ?? RED_FROM
  const lensMeta = meta.lenses.find((l) => l.key === filters.lens)
  const nationalOnly = lensMeta && lensMeta.levels.length === 1
  const themeGroup = String(filters.themeId).startsWith('group:') ? filters.themeId.slice(6) : null
  const themeId = filters.themeId && !themeGroup ? +filters.themeId : null
  // only the outlet→district links at or above the slider's minimum: the similarity and reprint edges belong
  // to the Outlets page (the answer is kept 10 minutes per URL by api.js, so the slider costs one call a value)
  const netQ = useApi('/api/network' + qs({ theme_id: themeGroup ? '' : filters.themeId, theme_group: themeGroup, week: filters.week, weeks: meta.window_weeks, kinds: 'outlet_region', min_weight: minEdge }), { deps: [version] })
  const network = netQ.data
  const loadError = netQ.error || geoErr
  const retryLoads = () => { netQ.retry(); if (geoErr) setGeoTick((n) => n + 1) }

  const groupIds = themeGroup ? new Set(meta.themes.filter((x) => x.group === themeGroup).map((x) => x.id)) : null
  const inScope = (tid) => (themeId ? tid === themeId : groupIds ? groupIds.has(tid) : true)
  const national = meta.regions.find((r) => r.level === 'national')

  // map values per district: gap (if this lens has regional need) else monitored coverage from the network
  const hasRegionalGap = cells.some((c) => regionsById.get(c.region_id)?.level === 'district' && !c.insufficient)
  const mode = hasRegionalGap ? 'gap' : 'coverage'
  const cellsByRegion = useMemo(() => {
    const m = new Map()
    if (mode === 'gap') {
      // the worst cell per district colours it: a short verdict before any other, then the largest gap
      const rank = (c) => (verdictOf(c, red) === 'short' ? 100 : 0) + (c.gap ?? -9)
      for (const c of cells) {
        if (!inScope(c.theme_id)) continue
        const prev = m.get(c.region_id)
        // the maps' "articles name this district" count is the all-source one (it matches the lines drawn)
        if (!prev || rank(c) > rank(prev)) m.set(c.region_id, { ...c, coverage: c.articles_all ?? c.coverage })
      }
    } else if (network) {
      for (const e of network.edges) {
        if (e.kind !== 'outlet_region') continue
        const rid = +e.target.slice(2)
        const p = m.get(rid) || { coverage: 0, flags: [] }
        p.coverage += e.weight
        m.set(rid, p)
      }
    }
    return m
  }, [cells, network, mode, themeId, themeGroup, red]) // eslint-disable-line react-hooks/exhaustive-deps

  const nationalCells = cells.filter((c) => c.region_id === national.id)
  const presentCats = useMemo(() => new Set((network?.nodes || []).filter((n) => n.type === 'outlet').map((n) => categoryOf(n, filters.colorBy))), [network, filters.colorBy])
  // theme group codes come from the API (only "gender" today); the catalogue has their Arabic
  const themeName = themeId ? pick(meta.themes.find((x) => x.id === themeId)) : themeGroup ? t('All {group} themes', { group: t(themeGroup) }) : t('All themes')
  // the weeks shown end on the Sunday of the selected week (filters.week is its Monday)
  const week = filters.week ? fmtDate(weekEnd(filters.week)) : ''
  const windowText = t('{n} weeks to {date}', { n: meta.window_weeks, date: week })
  const country = pick(meta.country)
  const caption = t('Source: Desert Watch monitored coverage (Google News, Google Alerts, GDELT, outlet and YouTube feeds, social posts Google indexes) · {window}.', { window: windowText }) + '\n' +
    t('Lines join outlets to districts their articles name. Monitored coverage only. We see Facebook only through the posts Google indexes, and Telegram not at all.') + '\n' + pick(meta.country.boundaries, 'attribution')
  // unplaced is counted over every source, so its share is of the all-source count
  const unplacedShare = nationalCells.length ? d3sum(nationalCells, (c) => c.breakdown?.unplaced || 0) / Math.max(1, d3sum(nationalCells, (c) => c.articles_all ?? c.coverage)) : null
  const lens = t(LENS_TEXT[filters.lens].label)
  const openDistrict = (rid) => {
    setSelected(rid)
    const cell = mode === 'gap' ? cellsByRegion.get(rid) : null
    if (cell?.theme_id) { openGap(cell.theme_id, rid, { from: 'map' }); return }
    openArticles({
      title: pick(regionsById.get(rid), 'name'), from: 'map',
      subtitle: t('Monitored articles naming this district, {n} weeks ending {week}.', { n: meta.window_weeks, week }),
      query: filters.week ? { region_id: rid, start: windowStart(filters.week, meta.window_weeks), end: weekEnd(filters.week) } : { region_id: rid, days: meta.window_weeks * 7 },
    })
  }
  // in coverage mode the district counts are sums of the links drawn, so a raised minimum leaves links out of them too
  const sentence = mode === 'gap'
    ? (themeId ? t('Districts shaded by under-coverage on the {lens} lens.', { lens }) : t('Districts shaded by under-coverage on the {lens} lens, worst theme per district.', { lens }))
    : t('The {lens} lens only has national figures, so districts show how many monitored articles name them. Pale districts with no lines are the deserts.', { lens })
      + (minEdge > 1 ? ` ${t('Links under {n} articles are hidden, and the district counts leave them out.', { n: minEdge })}` : '')

  return (
    <>
      {loadError && <ErrorBox error={loadError} onRetry={retryLoads} />}
      <div className="card-head">
        <div>
          {heading && <h2>{t('Who covers where · {theme}', { theme: themeName })}</h2>}
          <p className="sub">{sentence}{unplacedShare != null && ` ${t('{pct}% of articles name no district.', { pct: Math.round(unplacedShare * 100) })}`}</p>
        </div>
        <div className="row">
          <span className="seg" role="group" aria-label={t('Map view')}>
            <button aria-pressed={mapView === 'region'} onClick={() => pickView('region')}>{t('Sources by country')}</button>
            <button aria-pressed={mapView === 'libya'} onClick={() => pickView('libya')}>{t('Libya detail')}</button>
          </span>
          <label className="small row">{t('Hide links under')}
            <select value={minEdge} onChange={(e) => setMinEdge(+e.target.value)} aria-label={t('Minimum articles per link')}>
              {[1, 2, 3, 5, 10].map((n) => <option key={n} value={n}>{n}</option>)}</select> {t('articles', { n: minEdge })}</label>
          <ExportMenu svgRef={mapSvg} title={t('Who covers where in {country} — {theme}', { country, theme: themeName })} caption={caption} filename="who-covers-where" />
        </div>
      </div>
      {mapView === 'region' ? (
        <RegionalNetwork geo={geo?.districts} meta={meta} network={network} cellsByRegion={cellsByRegion} mode={mode}
          svgRef={mapSvg} minEdge={minEdge} red={red}
          onSelectRegion={openDistrict} />
      ) : <>
        <GeoNetwork geo={geo?.districts} macroGeo={geo?.macro} meta={meta} network={network} cellsByRegion={cellsByRegion}
          colorBy={filters.colorBy} mode={mode} lang={lang} svgRef={mapSvg} selectedRegion={selected} minEdge={minEdge} red={red}
          onSelectRegion={openDistrict}
          onSelectOutlet={(o) => openOutlet(+o.id.slice(2))} />
        <GeoLegend mode={mode} colorBy={filters.colorBy} present={presentCats} />
      </>}
      {outlets && (
        <>
          <h3>{t('Outlets in this view')}</h3>
          <p className="sub">{t('Click an outlet to see and suggest its categories. Categories need evidence; contested labels show their confidence.')}</p>
          <OutletStrip network={network} colorBy={filters.colorBy} onOpen={(id) => openOutlet(id)} />
        </>)}
    </>
  )
}

function OutletStrip({ network, colorBy, onOpen }) {
  if (!network) return null
  const outlets = network.nodes.filter((n) => n.type === 'outlet').sort((a, b) => b.articles - a.articles).slice(0, 30)
  const dim = DIMENSIONS[colorBy]
  return (
    <div className="chips">
      {outlets.map((o) => (
        <button key={o.id} className="chip" onClick={() => onOpen(+o.id.slice(2))} title={t(dim.values[categoryOf(o, colorBy)])}>
          <span className="dot" style={{ background: `var(--${dim.colors[categoryOf(o, colorBy)] || 'cat-unknown'})`, marginInlineEnd: 5 }} />
          <span dir="auto">{pick(o)}</span> <span className="muted num">{fmt(o.articles)}</span>
        </button>))}
    </div>
  )
}
