// Hero view: who covers where. Districts are shaded by gap (or by monitored coverage when
// the lens has no regional need data); outlets sit at their base and draw lines to the
// districts their articles name. Outlets based outside Libya sit in the right-hand margin,
// Libyan outlets with no known base sit in a strip at the bottom.
import * as d3 from 'd3'
import { useMemo, useRef, useState } from 'react'
import { INFO_FLAGS, DIMENSIONS, categoryColor, categoryOf, covFill, flagText, fmt, gapFill, gapLabel } from './scales'
import { HatchDefs, useSize, useTooltip } from './util'

const MARGIN_COL = 0.24

export default function GeoNetwork({ geo, macroGeo, meta, network, cellsByRegion, colorBy, mode, lang = 'en',
  selectedRegion, onSelectRegion, onSelectOutlet, svgRef, minEdge = 1 }) {
  const wrap = useRef(null)
  const W = useSize(wrap, 900)
  const narrow = W < 640
  const H = Math.round(narrow ? W * 1.25 : W * 0.66)
  const tip = useTooltip()
  const [hover, setHover] = useState(null) // node id
  const name = (o) => (lang === 'ar' && o.name_ar) ? o.name_ar : (o.name_en || o.name)

  const layout = useMemo(() => {
    if (!geo || !network) return null
    const mapW = narrow ? W : W * (1 - MARGIN_COL)
    const bottomStrip = 70
    const mapH = narrow ? H * 0.62 : H - bottomStrip
    const projection = d3.geoMercator().fitExtent([[12, 12], [mapW - 12, mapH - 12]], geo)
    const path = d3.geoPath(projection)
    const geoByName = new Map(geo.features.map((f) => [f.properties.shapeName, f]))
    const regionById = new Map(meta.regions.map((r) => [r.id, r]))
    const districts = meta.regions.filter((r) => r.level === 'district').map((r) => {
      const f = geoByName.get(meta.country.district_geo?.[r.slug])
      const c = f ? path.centroid(f) : projection([r.lon, r.lat])
      return { ...r, feature: f, x: c[0], y: c[1] }
    })
    const districtById = new Map(districts.map((d) => [d.id, d]))

    // outlets: weight = articles in window; keep those with any edge
    const outlets = network.nodes.filter((n) => n.type === 'outlet')
    const regionEdges = network.edges.filter((e) => e.kind === 'outlet_region' && e.weight >= minEdge)
    const edgesByOutlet = d3.group(regionEdges, (e) => e.source)
    const inside = [], outside = [], unplaced = []
    for (const o of outlets) {
      const scope = o.categories?.scope
      if (o.lat != null && o.lon != null && (scope !== 'international' && scope !== 'diaspora')) {
        const [x, y] = projection([o.lon, o.lat]); inside.push({ ...o, x, y })
      } else if (scope === 'international' || scope === 'diaspora' || o.base_country) outside.push(o)
      else unplaced.push(o)
    }
    const rScale = d3.scaleSqrt().domain([0, d3.max(outlets, (o) => o.articles) || 1]).range([3.5, narrow ? 11 : 15])
    // jitter co-located inside outlets in a small ring
    d3.groups(inside, (o) => `${Math.round(o.x)}:${Math.round(o.y)}`).forEach(([, g]) => {
      if (g.length < 2) return
      g.forEach((o, i) => { const a = (i / g.length) * 2 * Math.PI; o.x += Math.cos(a) * 14; o.y += Math.sin(a) * 14 })
    })
    // outside column, grouped by base country, sorted by volume
    const topN = (arr, n) => arr.sort((a, b) => b.articles - a.articles).slice(0, n)
    const out = topN(outside.filter((o) => o.articles > 0 || edgesByOutlet.has(o.id)), narrow ? 10 : 18)
    const colX = narrow ? 0 : mapW + 18
    const colTop = 26
    const colH = narrow ? 0 : mapH - colTop
    out.forEach((o, i) => {
      if (narrow) { o.x = 20 + (i % 5) * ((W - 40) / 4); o.y = mapH + 34 + Math.floor(i / 5) * 34 }
      else { o.x = colX + 10; o.y = colTop + (i + 0.5) * (colH / Math.max(out.length, 1)) }
    })
    const un = topN(unplaced.filter((o) => o.articles > 0), narrow ? 8 : 14)
    const stripY = narrow ? H - 26 : mapH + 40
    un.forEach((o, i) => { o.x = 24 + i * ((mapW - 48) / Math.max(un.length - 1, 1)); o.y = stripY })

    const placed = new Map([...inside, ...out, ...un].map((o) => [o.id, o]))
    const edges = regionEdges.map((e) => {
      const s = placed.get(e.source)
      const t = districtById.get(Number(e.target.slice(2)))
      return s && t ? { ...e, s, t } : null
    }).filter(Boolean)
    const wScale = d3.scaleSqrt().domain([1, d3.max(edges, (e) => e.weight) || 1]).range([0.8, 6])
    const incoming = d3.rollup(edges, (v) => ({ n: v.length, w: d3.sum(v, (e) => e.weight),
      colors: new Set(v.map((e) => categoryOf(e.s, colorBy))) }), (e) => e.t.id)
    return { mapW, mapH, path, districts, inside, out, un, edges, rScale, wScale, incoming, stripY, colX, regionById,
      macro: macroGeo ? macroGeo.features : [] }
  }, [geo, macroGeo, meta, network, W, H, narrow, colorBy, minEdge])

  if (!layout) return <div ref={wrap} className="viz"><div className="empty">Loading map…</div></div>
  const { mapW, mapH, path, districts, inside, out, un, edges, rScale, wScale, incoming } = layout
  const maxCov = d3.max(districts, (d) => cellsByRegion.get(d.id)?.coverage || 0) || 1
  const related = hover ? new Set(edges.filter((e) => e.source === hover || `r:${e.t.id}` === hover)
    .flatMap((e) => [e.source, `r:${e.t.id}`])) : null
  const fillFor = (d) => {
    const cell = cellsByRegion.get(d.id)
    if (mode === 'gap') return gapFill(cell) || 'url(#hatch)'
    return covFill(cell?.coverage || 0, maxCov)
  }
  const districtTip = (evt, d) => {
    const cell = cellsByRegion.get(d.id)
    const inc = incoming.get(d.id)
    tip.show(evt, (
      <div>
        <b>{d.name_en}</b> <span className="ar" dir="rtl">{d.name_ar}</span>
        <div className="muted small">{layout.regionById.get(d.parent_id)?.name_en}</div>
        <div style={{ marginTop: 4 }}>{fmt(cell?.coverage || 0)} articles name this district (4 weeks)</div>
        {mode === 'gap' && <div>{cell ? gapLabel(cell.insufficient ? null : cell.gap) : 'no need data'}</div>}
        <div>{inc ? `${inc.n} outlet${inc.n > 1 ? 's' : ''} shown covering it` : (cell?.coverage ? 'Links below the minimum are hidden' : 'No monitored outlet covers this district')}</div>
        {(cell?.flags || []).map((f) => <div key={f} className={INFO_FLAGS.has(f) ? "pill" : "pill flag"} style={{ marginTop: 3 }}>{flagText(f)}</div>)}
      </div>), wrap.current)
  }
  const outletTip = (evt, o) => tip.show(evt, (
    <div>
      <b>{o.name}</b> <span className="muted">{o.domain}</span>
      <div className="small">{o.base_city || o.base_country || 'Base not set'}</div>
      {Object.entries(o.categories || {}).map(([k, v]) => (
        <div key={k} className="small">{DIMENSIONS[k]?.label || k}: {DIMENSIONS[k]?.values?.[v] || v}
          {o.confidence?.[k] && <span className="muted"> ({o.confidence[k]})</span>}</div>))}
      <div style={{ marginTop: 4 }}>{fmt(o.articles)} articles on this selection</div>
    </div>), wrap.current)

  const curve = (e) => {
    const { s, t } = e
    const mx = (s.x + t.x) / 2, my = (s.y + t.y) / 2
    const dx = t.x - s.x, dy = t.y - s.y
    const k = 0.18
    return `M${s.x},${s.y} Q${mx - dy * k},${my + dx * k} ${t.x},${t.y}`
  }
  const unSet = new Set(un.map((o) => o.id))
  const labelled = new Set([...inside, ...out, ...un].sort((a, b) => b.articles - a.articles).slice(0, narrow ? 6 : 12).map((o) => o.id))

  return (
    <div ref={wrap} className="viz" onMouseLeave={() => { tip.hide(); setHover(null) }}>
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} role="img"
        aria-label="Map of Libya's districts with lines from news outlets to the districts their articles name">
        <HatchDefs />
        <g>
          {districts.map((d) => d.feature && (
            <path key={d.id} d={path(d.feature)} className="gap-fill"
              fill={fillFor(d)} stroke="var(--surface)" strokeWidth={selectedRegion === d.id ? 0 : 1}
              opacity={related && !related.has(`r:${d.id}`) ? 0.45 : 1}
              style={{ cursor: 'pointer' }}
              onMouseMove={(e) => { districtTip(e, d); setHover(`r:${d.id}`) }}
              onMouseLeave={() => { tip.hide(); setHover(null) }}
              onClick={() => onSelectRegion?.(d.id)} />
          ))}
          {layout.macro.map((f) => <path key={f.properties.shapeName} d={path(f)} fill="none" stroke="var(--ink-2)" strokeWidth={1.2} strokeOpacity={0.5} pointerEvents="none" />)}
          {selectedRegion && districts.filter((d) => d.id === selectedRegion && d.feature).map((d) =>
            <path key="sel" d={path(d.feature)} fill="none" stroke="var(--ink)" strokeWidth={2} pointerEvents="none" />)}
        </g>
        <g fill="none" strokeLinecap="round">
          {edges.map((e, i) => {
            const on = !hover || related?.has(e.source)
            const unplacedSrc = unSet.has(e.source)
            return <path key={i} d={curve(e)} stroke={categoryColor(colorBy, categoryOf(e.s, colorBy))}
              strokeWidth={wScale(e.weight)} strokeOpacity={on ? (hover ? 0.85 : unplacedSrc ? 0.14 : 0.4) : 0.05} pointerEvents="none" />
          })}
        </g>
        <g>
          {districts.map((d) => {
            const inc = incoming.get(d.id) || (cellsByRegion.get(d.id)?.coverage > 0)
            return (
              <g key={d.id} transform={`translate(${d.x},${d.y})`} pointerEvents="none">
                {!inc && <circle r={3} fill="none" stroke="var(--gap-5)" strokeWidth={1.5} />}
                {!narrow && <text y={inc ? -6 : -7} textAnchor="middle" style={{ fontSize: 10, fill: 'var(--ink-2)', paintOrder: 'stroke', stroke: 'var(--surface)', strokeWidth: 3 }}>
                  {lang === 'ar' ? d.name_ar : d.name_en}</text>}
              </g>)
          })}
        </g>
        {!narrow && out.length > 0 && <text x={layout.colX} y={14} style={{ fontSize: 11, fontWeight: 600 }}>Based outside Libya</text>}
        {un.length > 0 && <text x={12} y={layout.stripY - 18} style={{ fontSize: 11, fontWeight: 600 }}>Base not set yet — hover to see their links; open an outlet to set it</text>}
        <g>
          {[...inside, ...out, ...un].map((o) => {
            const dim = related && !related.has(o.id)
            const right = !narrow && out.includes(o)
            return (
              <g key={o.id} transform={`translate(${o.x},${o.y})`} style={{ cursor: 'pointer' }} opacity={dim ? 0.25 : 1}
                onMouseMove={(e) => { outletTip(e, o); setHover(o.id) }}
                onMouseLeave={() => { tip.hide(); setHover(null) }}
                onClick={() => onSelectOutlet?.(o)}>
                <circle r={rScale(o.articles) + 6} fill="transparent" />
                <circle r={rScale(o.articles)} fill={categoryColor(colorBy, categoryOf(o, colorBy))} stroke="var(--surface)" strokeWidth={2} />
                {(labelled.has(o.id) || hover === o.id || right) && (
                  <text x={right ? rScale(o.articles) + 5 : 0} y={right ? 4 : rScale(o.articles) + 12}
                    textAnchor={right ? 'start' : 'middle'}
                    style={{ fontSize: 10.5, fill: 'var(--ink)', paintOrder: 'stroke', stroke: 'var(--surface)', strokeWidth: 3 }}>
                    {o.name.length > 26 ? o.name.slice(0, 25) + '…' : o.name}</text>)}
              </g>)
          })}
        </g>
      </svg>
      {tip.node}
    </div>
  )
}

export function GeoLegend({ mode, colorBy, present }) {
  const dim = DIMENSIONS[colorBy]
  const values = Object.keys(dim.values).filter((v) => present?.has(v))
  return (
    <div className="legend" aria-label="Legend">
      {mode === 'gap' ? (
        <span>District: under-coverage <span className="ramp">{[1, 2, 3, 4, 5, 6].map((i) => <span key={i} style={{ background: `var(--gap-${i})` }} />)}</span>
          <span className="muted"> more →</span></span>
      ) : (
        <span>District: articles naming it <span className="ramp">{[1, 2, 3, 4, 5].map((i) => <span key={i} style={{ background: `var(--cov-${i})` }} />)}</span></span>
      )}
      {mode === 'gap' && <span><svg width="14" height="12" style={{ verticalAlign: -2, marginRight: 5 }}><HatchDefs id="lh" /><rect width="14" height="12" fill="url(#lh)" rx="2" /></svg>insufficient evidence</span>}
      <span><svg width="10" height="10" style={{ verticalAlign: -1, marginRight: 5 }}><circle cx="5" cy="5" r="3.5" fill="none" stroke="var(--gap-5)" strokeWidth="1.5" /></svg>no outlet covers it</span>
      <span className="muted">· Outlets by {dim.label.toLowerCase()}:</span>
      {values.map((v) => <span key={v}><span className="sw" style={{ background: categoryColor(colorBy, v), borderRadius: '50%' }} />{dim.values[v]}</span>)}
    </div>
  )
}
