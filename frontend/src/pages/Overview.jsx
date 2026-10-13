import * as d3 from 'd3'
import { useEffect, useMemo, useRef, useState } from 'react'
import { api, qs, track } from '../api'
import { useApp } from '../App'
import Filters from '../components/Filters'
import GeoNetwork, { GeoLegend } from '../charts/GeoNetwork'
import Heatmap from '../charts/Heatmap'
import { LanguageBalance } from '../charts/Balance'
import { INFO_FLAGS, DIMENSIONS, LENS_TEXT, categoryOf, flagText, fmt, gapFill, gapLabel } from '../charts/scales'
import { ExportMenu } from '../charts/util'
import SourceHealth from '../components/SourceHealth'

let geoCache = null
async function loadGeo(meta) {
  if (geoCache) return geoCache
  const b = meta.country.boundaries
  const [d, m] = await Promise.all([fetch(`/geo/${b.districts_geojson}`).then((r) => r.json()),
    b.macro_geojson ? fetch(`/geo/${b.macro_geojson}`).then((r) => r.json()) : null])
  // d3-geo uses spherical winding: a polygon whose area exceeds a hemisphere is "inside out"
  // (RFC 7946 files wind the other way). Reverse such rings.
  const rewind = (fc) => { fc.features.forEach((f) => {
    if (d3.geoArea(f) <= 2 * Math.PI) return
    const g = f.geometry
    const rev = (poly) => poly.map((ring) => ring.slice().reverse())
    if (g.type === 'Polygon') g.coordinates = rev(g.coordinates)
    else if (g.type === 'MultiPolygon') g.coordinates = g.coordinates.map(rev) }); return fc }
  geoCache = { districts: rewind(d), macro: m ? rewind(m) : null }
  return geoCache
}

export default function Overview() {
  const { meta, filters, lang, openGap, openOutlet, version } = useApp()
  const [geo, setGeo] = useState(null)
  const [cells, setCells] = useState([])
  const [network, setNetwork] = useState(null)
  const [selected, setSelected] = useState(null)
  const [minEdge, setMinEdge] = useState(2)
  const mapSvg = useRef(null), heatSvg = useRef(null), langSvg = useRef(null)

  useEffect(() => { loadGeo(meta).then(setGeo) }, [meta])
  const regionsById = useMemo(() => new Map(meta.regions.map((r) => [r.id, r])), [meta])
  const [regionalContext, setRegionalContext] = useState([])
  const lensMeta = meta.lenses.find((l) => l.key === filters.lens)
  const nationalOnly = lensMeta && lensMeta.levels.length === 1
  useEffect(() => {
    if (!filters.week) return
    api('/api/cells' + qs({ lens: filters.lens, week: filters.week })).then((r) => setCells(r.cells))
    // A national-only lens still has regional coverage counts worth showing (unscored, hatched).
    if (nationalOnly) api('/api/cells' + qs({ lens: 'journalist', week: filters.week })).then((r) =>
      setRegionalContext(r.cells.filter((c) => regionsById.get(c.region_id)?.level !== 'national').map((c) => ({ ...c, insufficient: true, gap: null, flags: [] }))))
    else setRegionalContext([])
  }, [filters.lens, filters.week, version, nationalOnly])
  useEffect(() => {
    const g = String(filters.themeId).startsWith('group:') ? filters.themeId.slice(6) : null
    api('/api/network' + qs({ theme_id: g ? '' : filters.themeId, theme_group: g, week: filters.week, weeks: meta.window_weeks })).then(setNetwork)
  }, [filters.themeId, filters.week, meta.window_weeks, version])

  const themeGroup = String(filters.themeId).startsWith('group:') ? filters.themeId.slice(6) : null
  const themeId = filters.themeId && !themeGroup ? +filters.themeId : null
  const groupIds = themeGroup ? new Set(meta.themes.filter((t) => t.group === themeGroup).map((t) => t.id)) : null
  const inScope = (tid) => (themeId ? tid === themeId : groupIds ? groupIds.has(tid) : true)
  const national = meta.regions.find((r) => r.level === 'national')

  // map values per district: gap (if this lens has regional need) else monitored coverage from the network
  const hasRegionalGap = cells.some((c) => regionsById.get(c.region_id)?.level === 'district' && !c.insufficient)
  const mode = hasRegionalGap ? 'gap' : 'coverage'
  const cellsByRegion = useMemo(() => {
    const m = new Map()
    if (mode === 'gap') {
      for (const c of cells) {
        if (!inScope(c.theme_id)) continue
        const prev = m.get(c.region_id)
        if (!prev || (c.gap ?? -9) > (prev.gap ?? -9)) m.set(c.region_id, c)
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
  }, [cells, network, mode, themeId])

  const nationalCells = cells.filter((c) => c.region_id === national.id)
  const ranked = useMemo(() => {
    const ok = cells.filter((c) => !c.insufficient && c.gap != null && inScope(c.theme_id))
      .sort((a, b) => b.gap - a.gap)
    let top = ok.filter((c) => c.gap >= 0.15).slice(0, 7)
    if (!top.length) top = ok.slice(0, 5).map((c) => ({ ...c, fallback: true }))
    // exploration slot: one random lower-ranked cell so rankings don't only reinforce themselves
    const rest = ok.filter((c) => !top.includes(c))
    if (rest.length && top.length >= 3 && !top[0].fallback) {
      const pick = rest[Math.floor(Math.random() * rest.length)]
      top.splice(3, 0, { ...pick, explore: true })
    }
    return top
  }, [cells, themeId, themeGroup])
  useEffect(() => {
    ranked.forEach((c, i) => track('impression', 'gap', `${c.theme_id}:${c.region_id}`, { position: i, lens: filters.lens, explore: !!c.explore, list: 'top_gaps' }))
  }, [ranked, filters.lens])

  const fallback = ranked.length > 0 && ranked[0].fallback
  const presentCats = useMemo(() => new Set((network?.nodes || []).filter((n) => n.type === 'outlet').map((n) => categoryOf(n, filters.colorBy))), [network, filters.colorBy])
  const heatRegions = [national, ...meta.regions.filter((r) => r.level === 'macro')]
  const feedback = Object.fromEntries(cells.map((c) => [`${c.theme_id}:${c.region_id}`, c.votes]))
  const themeName = themeId ? meta.themes.find((t) => t.id === themeId)?.name_en : themeGroup ? `All ${themeGroup} themes` : 'All themes'
  const caption = `Source: Desert Watch monitored coverage (Google News, GDELT, outlet RSS) · ${meta.window_weeks}-week window ending ${filters.week}.\n` +
    `Lines join outlets to districts their articles name. Monitored coverage only; Facebook/Telegram-only reporting is not captured.\n${meta.country.boundaries?.attribution || ''}`
  const unplacedShare = nationalCells.length ? d3.sum(nationalCells, (c) => c.breakdown?.unplaced || 0) / Math.max(1, d3.sum(nationalCells, (c) => c.coverage)) : null
  const lensInfo = LENS_TEXT[filters.lens]

  return (
    <>
      <Filters />
      <main className="page">
        <SourceHealth compact />
        <section className="card">
            <div className="card-head">
              <div>
                <h2>Who covers where · {themeName}</h2>
                <p className="sub">{mode === 'gap'
                  ? `Districts shaded by under-coverage (${lensInfo.label} lens${themeId ? '' : ', worst theme per district'}).`
                  : `${lensInfo.label} need data is national-only, so districts show how many monitored articles name them. Pale districts with no lines are the deserts.`}
                  {unplacedShare != null && ` ${Math.round(unplacedShare * 100)}% of articles name no district.`}</p>
              </div>
              <div className="row">
                <label className="small row">Hide links under
                  <select value={minEdge} onChange={(e) => setMinEdge(+e.target.value)} aria-label="Minimum articles per link">
                    {[1, 2, 3, 5, 10].map((n) => <option key={n} value={n}>{n}</option>)}</select> articles</label>
                <ExportMenu svgRef={mapSvg} title={`Who covers where in ${meta.country.name_en} — ${themeName}`} caption={caption} filename="who-covers-where" />
              </div>
            </div>
            <GeoNetwork geo={geo?.districts} macroGeo={geo?.macro} meta={meta} network={network} cellsByRegion={cellsByRegion}
              colorBy={filters.colorBy} mode={mode} lang={lang} svgRef={mapSvg} selectedRegion={selected} minEdge={minEdge}
              onSelectRegion={(rid) => { setSelected(rid); openGap(themeId || meta.themes.find((t) => inScope(t.id))?.id || meta.themes[0].id, rid, { from: 'map' }) }}
              onSelectOutlet={(o) => openOutlet(+o.id.slice(2))} />
            <GeoLegend mode={mode} colorBy={filters.colorBy} present={presentCats} />
          </section>
        <div className="grid halves" style={{ marginTop: 16 }}>
          <section className="card">
            <h2>{fallback ? 'Least covered this week' : 'Biggest gaps this week'}</h2>
            <p className="sub">{lensInfo.blurb}. Click to review, vote and comment.</p>
            {fallback && <p className="small muted">No theme is clearly falling behind its need signal this week; these are the least covered relative to it.</p>}
            {ranked.length === 0 && <div className="empty">No cells with enough evidence for this lens and week.</div>}
            {ranked.map((c, i) => {
              const t = meta.themes.find((x) => x.id === c.theme_id)
              const r = regionsById.get(c.region_id)
              return (
                <div key={`${c.theme_id}:${c.region_id}`} className="gapcard" role="button" tabIndex={0}
                  onClick={() => openGap(c.theme_id, c.region_id, { position: i, explore: !!c.explore, list: 'top_gaps' })}
                  onKeyDown={(e) => e.key === 'Enter' && openGap(c.theme_id, c.region_id, { position: i })}>
                  <div>
                    <div className="t">{lang === 'ar' ? t?.name_ar : t?.name_en} · <span style={{ fontWeight: 400 }}>{lang === 'ar' ? r?.name_ar : r?.name_en}</span></div>
                    <div className="small muted">{fmt(c.coverage)} articles vs {fmt(c.need)} {lensInfo.unit} · {gapLabel(c.gap)}</div>
                    <div className="row" style={{ marginTop: 4 }}>
                      {c.explore && <span className="pill" title="Shown to check the ranking isn't only reinforcing itself">exploring</span>}
                      {(c.flags || []).map((f) => <span key={f} className={INFO_FLAGS.has(f) ? "pill" : "pill flag"}>{flagText(f)}</span>)}
                      {c.votes?.real > 0 && <span className="pill">✓ {c.votes.real} real</span>}
                      {c.votes?.covered > 0 && <span className="pill">{c.votes.covered} covered</span>}
                      {c.comments > 0 && <span className="pill">💬 {c.comments}</span>}
                      {c.claims?.working > 0 && <span className="pill ok">someone is on it</span>}
                    </div>
                  </div>
                  <span className="dot" style={{ width: 14, height: 14, borderRadius: 4, background: gapFill(c) || 'var(--surface-2)' }} aria-hidden="true" />
                </div>)
            })}
          </section>
          <section className="card">
            <div className="card-head">
              <div><h2>Arabic vs English coverage</h2><p className="sub">Monitored articles nationally, {meta.window_weeks} weeks ending {filters.week}.</p></div>
              <ExportMenu svgRef={langSvg} title={`Arabic vs English coverage of ${meta.country.name_en}`} caption={caption} filename="language-balance" />
            </div>
            <LanguageBalance themes={meta.themes.filter((t) => inScope(t.id))} cells={nationalCells} lang={lang} svgRef={langSvg} />
          </section>
        </div>
        <section className="card" style={{ marginTop: 16 }}>
          <div className="card-head">
            <div><h2>Gap by theme and region</h2>
              <p className="sub">{lensInfo.label} lens · {meta.window_weeks}-week window ending {filters.week}. Hatched = not enough need data to score{nationalOnly ? ` (this lens is national-only; regional columns show coverage counts until regional need data arrives)` : ''}.</p></div>
            <ExportMenu svgRef={heatSvg} title={`Coverage gaps by theme and region — ${meta.country.name_en}`} caption={caption} filename="gap-heatmap" />
          </div>
          <Heatmap themes={meta.themes.filter((t) => inScope(t.id))} regions={heatRegions} cells={[...cells, ...regionalContext]} svgRef={heatSvg} unit={lensInfo.unit} lang={lang}
            feedback={feedback} onSelect={(t, r) => openGap(t, r, { from: 'heatmap' })} />
        </section>
        <section className="card" style={{ marginTop: 16 }}>
          <h2>Outlets in this view</h2>
          <p className="sub">Click an outlet to see and suggest its categories. Categories need evidence; contested labels show their confidence.</p>
          <OutletStrip network={network} colorBy={filters.colorBy} onOpen={(id) => openOutlet(id)} />
        </section>
      </main>
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
        <button key={o.id} className="chip" onClick={() => onOpen(+o.id.slice(2))} title={dim.values[categoryOf(o, colorBy)]}>
          <span className="dot" style={{ background: `var(--${dim.colors[categoryOf(o, colorBy)] || 'cat-unknown'})`, marginRight: 5 }} />
          {o.name} <span className="muted num">{fmt(o.articles)}</span>
        </button>))}
    </div>
  )
}
