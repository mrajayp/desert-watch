// Regional view of "who covers where": sources outside Libya are grouped by the country they are
// based in and pinned to that country's media hub, so positions are geographic and stable over
// time. Arcs run from each source country into the Libyan districts its articles name.
import * as d3 from 'd3'
import { useMemo, useRef, useState } from 'react'
import { feature } from 'topojson-client'
import world from 'world-atlas/countries-110m.json'
import { covFill, fmt, gapFill } from './scales'
import { HatchDefs, useSize, useTooltip } from './util'
import { pick, t, tn, isAr } from '../i18n'

// Media hub per country (lon, lat). Uncontested reference points, not outlet addresses.
export const HUBS = {
  'United Kingdom': [-0.13, 51.5], Qatar: [51.53, 25.29], 'United Arab Emirates': [55.27, 25.2], Egypt: [31.24, 30.04],
  Turkey: [28.98, 41.01], France: [2.35, 48.86], Italy: [12.5, 41.9], Lebanon: [35.5, 33.89], 'Saudi Arabia': [46.68, 24.71],
  Greece: [23.73, 37.98], Malta: [14.51, 35.9], Morocco: [-6.84, 34.02], Syria: [36.29, 33.51], Israel: [34.78, 32.08],
  Palestine: [35.2, 31.9], Nigeria: [3.38, 6.52], Ukraine: [30.52, 50.45], 'United States': [-77.04, 38.9],
  Switzerland: [6.14, 46.2], Tunisia: [10.18, 36.81], Germany: [13.4, 52.52], Jordan: [35.93, 31.95], Algeria: [3.06, 36.75],
  Sudan: [32.56, 15.5], Iraq: [44.37, 33.31], Russia: [37.62, 55.75], Spain: [-3.7, 40.42], Belgium: [4.35, 50.85],
  Netherlands: [4.9, 52.37], Kuwait: [47.98, 29.37], Bahrain: [50.58, 26.22], Oman: [58.4, 23.59], Chad: [15.04, 12.11],
  Niger: [2.11, 13.51], Mali: [-8.0, 12.64], Canada: [-75.7, 45.42], Iran: [51.39, 35.69], Austria: [16.37, 48.21],
  Sweden: [18.07, 59.33], Norway: [10.75, 59.91], Denmark: [12.57, 55.68], Portugal: [-9.14, 38.72], Yemen: [44.19, 15.37],
  India: [77.21, 28.61], Pakistan: [73.05, 33.68], Australia: [149.13, -35.28],
}
// The API sends an outlet's base country in English; this gives its name in the interface language.
export function countryName(c) {
  if (!c) return ''
  const names = {
    Libya: t('Libya'), 'United Kingdom': t('United Kingdom'), Qatar: t('Qatar'), 'United Arab Emirates': t('United Arab Emirates'),
    Egypt: t('Egypt'), Turkey: t('Turkey'), France: t('France'), Italy: t('Italy'), Lebanon: t('Lebanon'), 'Saudi Arabia': t('Saudi Arabia'),
    Greece: t('Greece'), Malta: t('Malta'), Morocco: t('Morocco'), Syria: t('Syria'), Israel: t('Israel'), Palestine: t('Palestine'),
    Nigeria: t('Nigeria'), Ukraine: t('Ukraine'), 'United States': t('United States'), Switzerland: t('Switzerland'), Tunisia: t('Tunisia'),
    Germany: t('Germany'), Jordan: t('Jordan'), Algeria: t('Algeria'), Sudan: t('Sudan'), Iraq: t('Iraq'), Russia: t('Russia'),
    Spain: t('Spain'), Belgium: t('Belgium'), Netherlands: t('Netherlands'), Kuwait: t('Kuwait'), Bahrain: t('Bahrain'), Oman: t('Oman'),
    Chad: t('Chad'), Niger: t('Niger'), Mali: t('Mali'), Canada: t('Canada'), Iran: t('Iran'), Austria: t('Austria'), Sweden: t('Sweden'),
    Norway: t('Norway'), Denmark: t('Denmark'), Portugal: t('Portugal'), Yemen: t('Yemen'), India: t('India'), Pakistan: t('Pakistan'),
    Australia: t('Australia'),
  }
  return names[c] || (isAr() && regionAr(c)) || c
}

// any other country: the browser's own Arabic name, found through its English name
let REGIONS = null
function regionAr(name) {
  try {
    if (!REGIONS) {
      const en = new Intl.DisplayNames(['en'], { type: 'region' }), ar = new Intl.DisplayNames(['ar'], { type: 'region' })
      REGIONS = new Map()
      for (let a = 65; a < 91; a++) for (let b = 65; b < 91; b++) {
        const code = String.fromCharCode(a, b)
        const n = en.of(code)
        if (n && n !== code) REGIONS.set(n, ar.of(code))
      }
    }
    return REGIONS.get(name) || ''
  } catch { return '' }
}
const EXTENT = { type: 'MultiPoint', coordinates: [[-11, 6], [57, 6], [-11, 55], [57, 55]] } // i18n-ok: GeoJSON geometry type
const LIBYA_UNPLACED = [17.0, 34.6] // in the sea north of Sirte: "Libyan outlets, base not set"
const UNKNOWN = [-6.5, 20.0]         // over the Sahara west: "origin unknown"

export default function RegionalNetwork({ geo, meta, network, cellsByRegion, mode, svgRef, onSelectRegion, minEdge = 1 }) {
  const wrap = useRef(null)
  const W = useSize(wrap, 1000)
  const H = Math.round(W * (W < 640 ? 0.95 : 0.62))
  const tip = useTooltip()
  const [hover, setHover] = useState(null)

  const countries = useMemo(() => feature(world, world.objects.countries).features, [])
  const layout = useMemo(() => {
    if (!geo || !network) return null
    const projection = d3.geoMercator().fitExtent([[8, 8], [W - 8, H - 8]], EXTENT)
    const path = d3.geoPath(projection)
    const inFrame = ([px, py]) => px >= 0 && px <= W && py >= 0 && py <= H
    const clamp = ([px, py]) => [Math.max(24, Math.min(W - 24, px)), Math.max(24, Math.min(H - 24, py))]
    const geoByName = new Map(geo.features.map((f) => [f.properties.shapeName, f]))
    const districts = meta.regions.filter((r) => r.level === 'district').map((r) => {
      const f = geoByName.get(meta.country.district_geo?.[r.slug])
      const c = f ? path.centroid(f) : projection([r.lon, r.lat])
      return { ...r, feature: f, x: c[0], y: c[1] }
    })
    const districtById = new Map(districts.map((d) => [d.id, d]))
    const outlets = network.nodes.filter((n) => n.type === 'outlet')
    // group outlets: foreign by base country; Libyan with a base individually; the rest aggregated
    const groupOf = (o) => {
      const scope = o.categories?.scope
      if (o.base_country && o.base_country !== 'Libya') return `c:${o.base_country}`
      if (scope === 'libyan' || o.base_city) return o.lat != null ? `o:${o.id}` : 'libya-unplaced'
      if (scope === 'international' || scope === 'diaspora') return 'intl-unknown'
      return 'unknown'
    }
    const groups = new Map()
    for (const o of outlets) {
      const k = groupOf(o)
      if (!groups.has(k)) groups.set(k, { key: k, outlets: [], articles: 0 })
      const g = groups.get(k)
      g.outlets.push(o)
      g.articles += o.articles || 0
    }
    for (const g of groups.values()) {
      let lonlat, label
      if (g.key.startsWith('c:')) { label = countryName(g.key.slice(2)); lonlat = HUBS[g.key.slice(2)] }
      else if (g.key.startsWith('o:')) { const o = g.outlets[0]; label = pick(o); lonlat = [o.lon, o.lat] }
      else if (g.key === 'libya-unplaced') { label = t('Libyan outlets · base not set'); lonlat = LIBYA_UNPLACED }
      else if (g.key === 'intl-unknown') { label = t('International · country not set'); lonlat = [UNKNOWN[0], UNKNOWN[1] - 4] }
      else { label = t('Origin unknown'); lonlat = UNKNOWN }
      if (!lonlat) { label = t('{label} (no hub)', { label }); lonlat = UNKNOWN }
      const p = projection(lonlat)
      g.offscreen = !inFrame(p)
      ;[g.x, g.y] = clamp(p)
      g.label = label
    }
    const outletGroup = new Map(outlets.map((o) => [o.id, groupOf(o)]))
    const agg = new Map()
    for (const e of network.edges) {
      if (e.kind !== 'outlet_region' || e.weight < minEdge) continue
      const t = districtById.get(+e.target.slice(2))
      const gk = outletGroup.get(e.source)
      if (!t || !gk) continue
      const k = `${gk}|${t.id}`
      agg.set(k, (agg.get(k) || 0) + e.weight)
    }
    const arcs = [...agg.entries()].map(([k, w]) => { const [gk, tid] = k.split('|'); return { g: groups.get(gk), t: districtById.get(+tid), w } })
    const wScale = d3.scaleSqrt().domain([1, d3.max(arcs, (a) => a.w) || 1]).range([0.7, 7])
    const rScale = d3.scaleSqrt().domain([0, d3.max([...groups.values()], (g) => g.articles) || 1]).range([3, Math.max(14, W / 40)])
    const reach = d3.rollup(arcs, (v) => v.length, (a) => a.g.key)
    return { path, districts, groups: [...groups.values()].filter((g) => g.articles > 0 || reach.get(g.key)), arcs, wScale, rScale, reach }
  }, [geo, network, meta, W, H, minEdge])

  if (!layout) return <div ref={wrap} className="viz"><div className="empty">{t('Loading map…')}</div></div>
  const { path, districts, groups, arcs, wScale, rScale, reach } = layout
  const maxCov = d3.max(districts, (d) => cellsByRegion.get(d.id)?.coverage || 0) || 1
  const fillFor = (d) => (mode === 'gap' ? gapFill(cellsByRegion.get(d.id)) || 'url(#hatch)' : covFill(cellsByRegion.get(d.id)?.coverage || 0, maxCov)) // i18n-ok: SVG pattern reference, not shown
  const curve = (a) => {
    const sx = a.g.x, sy = a.g.y, tx = a.t.x, ty = a.t.y
    const mx = (sx + tx) / 2, my = (sy + ty) / 2, dx = tx - sx, dy = ty - sy
    return `M${sx},${sy} Q${mx - dy * 0.2},${my + dx * 0.2} ${tx},${ty}`
  }
  const isForeign = (g) => g.key.startsWith('c:') || g.key === 'intl-unknown'
  const colorFor = (g) => (isForeign(g) ? 'var(--scope-international)' : g.key === 'unknown' ? 'var(--cat-unknown)' : 'var(--scope-libyan)')
  const groupTip = (evt, g) => tip.show(evt, (
    <div><b dir="auto">{g.label}</b>{g.offscreen && <span className="muted"> {t('(outside the map frame)')}</span>}
      <div>{t('{count} articles', { count: fmt(g.articles) })} · {tn(g.outlets.length, '{n} outlet', '{n} outlets')} · {t('{n} districts named', { n: reach.get(g.key) || 0 })}</div>
      <div className="small" style={{ marginTop: 4 }}>{g.outlets.sort((a, b) => b.articles - a.articles).slice(0, 8).map((o) => `${pick(o)} (${o.articles})`).join(' · ')}
        {g.outlets.length > 8 ? ` ${t('+{n} more', { n: g.outlets.length - 8 })}` : ''}</div></div>), wrap.current)
  const libya = countries.find((c) => c.properties.name === 'Libya')

  return (
    <div ref={wrap} className="viz" onMouseLeave={() => { tip.hide(); setHover(null) }}>
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} style={{ overflow: "hidden", borderRadius: 6 }} role="img" aria-label={t('Regional map: where the sources covering Libya are based, with arcs to the districts they cover')}>
        <HatchDefs />
        <rect width={W} height={H} fill="var(--surface)" />
        {countries.map((c) => c !== libya && <path key={c.id || c.properties.name} d={path(c)} fill="var(--surface-2)" stroke="var(--grid)" strokeWidth={0.6} />)}
        {districts.map((d) => d.feature && (
          <path key={d.id} d={path(d.feature)} fill={fillFor(d)} stroke="var(--surface)" strokeWidth={0.6} style={{ cursor: 'pointer' }}
            onMouseMove={(e) => tip.show(e, <div><b>{pick(d)}</b><div>{t('{count} articles name it', { count: fmt(cellsByRegion.get(d.id)?.coverage || 0) })}</div></div>, wrap.current)}
            onClick={() => onSelectRegion?.(d.id)} />))}
        {libya && <path d={path(libya)} fill="none" stroke="var(--ink-2)" strokeWidth={1.2} pointerEvents="none" />}
        <g fill="none" strokeLinecap="round">
          {arcs.map((a, i) => {
            const on = !hover || hover === a.g.key
            return <path key={i} d={curve(a)} stroke={colorFor(a.g)} strokeWidth={wScale(a.w)} strokeOpacity={on ? (hover ? 0.85 : 0.35) : 0.04} pointerEvents="none" />
          })}
        </g>
        {groups.sort((a, b) => b.articles - a.articles).map((g) => {
          const r = rScale(g.articles)
          const dim = hover && hover !== g.key
          const rightSide = g.x < W * 0.8
          return (
            <g key={g.key} transform={`translate(${g.x},${g.y})`} opacity={dim ? 0.3 : 1} style={{ cursor: 'pointer' }}
              onMouseMove={(e) => { setHover(g.key); groupTip(e, g) }} onMouseLeave={() => { setHover(null); tip.hide() }}>
              <circle r={r + 6} fill="transparent" />
              <circle r={r} fill={colorFor(g)} fillOpacity={0.9} stroke="var(--surface)" strokeWidth={2} />
              {(r > 6 || hover === g.key || isForeign(g)) && (
                <text x={rightSide ? r + 4 : -(r + 4)} y={4} textAnchor={rightSide ? 'start' : 'end'}
                  style={{ fontSize: 11, fontWeight: 600, fill: 'var(--ink)', paintOrder: 'stroke', stroke: 'var(--surface)', strokeWidth: 3 }}>
                  {g.offscreen ? `${g.label} →` : g.label}</text>)}
            </g>)
        })}
      </svg>
      {tip.node}
      <div className="legend">
        <span><span className="sw" style={{ background: 'var(--scope-international)', borderRadius: '50%' }} />{t('Sources based outside Libya, grouped by country (at its media hub)')}</span>
        <span><span className="sw" style={{ background: 'var(--scope-libyan)', borderRadius: '50%' }} />{t('Libyan outlets')}</span>
        <span><span className="sw" style={{ background: 'var(--cat-unknown)', borderRadius: '50%' }} />{t('Origin not set')}</span>
        <span className="muted">{t('Bubble = articles in the window · arc = articles naming the district · → country is beyond the frame')}</span>
      </div>
    </div>
  )
}
