// Coverage-cluster map (design language adapted from published network-map reports):
// position = similarity (similarity links are used for layout but NOT drawn), colour = cluster,
// clusters named in plain words with colour-filled tags at the cluster edge, reprint arrows
// drawn because there the link itself is the evidence. A legend table sits beside it.
import { extent as d3extent, forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY, least as d3least, max as d3max, mean as d3mean, scaleSqrt, sum as d3sum } from 'd3'
import { Fragment, useMemo, useRef, useState } from 'react'
import { fmtNum, isAr, pick, t } from '../i18n'

const N_ = (s) => s // marks English for the catalogue; translated with t() when shown
import { fmt } from './scales'
import { useSize, useTooltip } from './util'

// Cluster tags from the API: the main language ("Arabic") and a scope code ("libyan"), shown as they are in English.
const TAG = { Arabic: N_('Arabic'), English: N_('English'), UND: N_('Language not detected'), libyan: N_('libyan'), international: N_('international'), diaspora: N_('diaspora') }
export const tagText = (x) => (TAG[x] ? t(TAG[x]) : x)
// a decimal with the interface language's decimal mark: num(1.4) or num(12.345, 1) like (12.345).toFixed(1)
const num = (v, d) => fmtNum(v, d == null ? { useGrouping: false } : { minimumFractionDigits: d, maximumFractionDigits: d, useGrouping: false })

// Five validated slots (adjacent-pair check, light + dark); every cluster also carries a
// text tag, so identity never relies on colour alone. Clusters beyond five fold into "Other".
export const CLUSTER_SLOTS = ['al-1', 'al-2', 'al-3', 'al-4', 'al-5']
export const clusterColor = (rank) => (rank != null && rank < CLUSTER_SLOTS.length ? `var(--${CLUSTER_SLOTS[rank]})` : 'var(--cat-unknown)')


export function layoutClusters(network, clusters, rankOf, W, H) {
  if (!network || !clusters.length) return null
  const memberIds = new Set(clusters.flatMap((c) => c.members))
  const byId = new Map(network.nodes.filter((n) => n.type === 'outlet').map((n) => [n.id, n]))
  const nodes = [...memberIds].filter((id) => byId.has(id)).map((id) => ({ ...byId.get(id), rank: rankOf.get(id) }))
  const keep = new Set(nodes.map((n) => n.id))
  const sim = network.edges.filter((e) => e.kind === 'outlet_outlet' && keep.has(e.source) && keep.has(e.target)).map((e) => ({ ...e }))
  const reprint = network.edges.filter((e) => e.kind === 'syndication' && e.weight >= 2 && keep.has(e.source) && keep.has(e.target)).map((e) => ({ ...e }))
  const r = scaleSqrt().domain([0, d3max(nodes, (n) => n.articles) || 1]).range([3.5, 16])
  // cluster centres on a circle pull each community together, so clusters read as regions
  const ranks = [...new Set(nodes.map((n) => Math.min(n.rank ?? 99, 6)))].sort((a, b) => a - b)
  const centre = new Map(ranks.map((k, i) => {
    const a = (i / ranks.length) * 2 * Math.PI - Math.PI / 2
    return [k, [W / 2 + Math.cos(a) * W * 0.27, H / 2 + Math.sin(a) * H * 0.3]]
  }))
  const cKey = (n) => Math.min(n.rank ?? 99, 6)
  const simu = forceSimulation(nodes)
    .force('link', forceLink(sim).id((d) => d.id).distance(40).strength((l) => 0.15 + 0.4 * l.weight))
    .force('charge', forceManyBody().strength(-45))
    .force('collide', forceCollide((d) => r(d.articles) + 2.5))
    .force('x', forceX((d) => centre.get(cKey(d))[0]).strength(0.12))
    .force('y', forceY((d) => centre.get(cKey(d))[1]).strength(0.12))
    .stop()
  for (let i = 0; i < 320; i++) simu.tick()
  const [x0, x1] = d3extent(nodes, (n) => n.x), [y0, y1] = d3extent(nodes, (n) => n.y)
  const pad = 48
  const k = Math.min((W - 2 * pad) / Math.max(1, x1 - x0), (H - 2 * pad) / Math.max(1, y1 - y0), 1.5)
  nodes.forEach((n) => { n.x = pad + (n.x - x0) * k + ((W - 2 * pad) - (x1 - x0) * k) / 2; n.y = pad + (n.y - y0) * k + ((H - 2 * pad) - (y1 - y0) * k) / 2 })
  const nodeById = new Map(nodes.map((n) => [n.id, n]))
  const reprints = reprint.map((e) => ({ ...e, s: nodeById.get(e.source), t: nodeById.get(e.target) })).filter((e) => e.s && e.t)
  const sims = sim.map((e) => ({ ...e, s: e.source, t: e.target }))
  // tag anchor: top-most point of each named cluster
  const tags = clusters.filter((c) => c.rank < CLUSTER_SLOTS.length).map((c) => {
    const pts = nodes.filter((n) => n.rank === c.rank)
    if (!pts.length) return null
    const top = d3least(pts, (n) => n.y - r(n.articles))
    const cx = d3mean(pts, (n) => n.x)
    return { c, x: Math.max(70, Math.min(W - 70, cx)), y: Math.max(14, top.y - r(top.articles) - 14) }
  }).filter(Boolean)
  // de-overlap tags: push later tags down while they collide with an earlier one
  const tagW = (t) => Math.min(220, 14 + t.c.name.length * 6.4)
  tags.sort((a, b) => a.y - b.y)
  for (let i = 0; i < tags.length; i++) {
    for (let tries = 0; tries < 12; tries++) {
      const hit = tags.slice(0, i).find((o) => Math.abs(o.y - tags[i].y) < 23 && Math.abs(o.x - tags[i].x) < (tagW(o) + tagW(tags[i])) / 2 + 16)
      if (!hit) break
      tags[i].y = hit.y + 24
    }
    tags[i].y = Math.min(H - 12, tags[i].y)
  }
  return { nodes, reprints, sims, r, tags }
}

export default function ClusterMap({ network, clusters, showReprints = true, showSimilarity = false, lang = 'en', onSelectOutlet, svgRef, highlight, setHighlight }) {
  const wrap = useRef(null)
  const W = useSize(wrap, 800)
  const H = Math.round(Math.min(640, Math.max(400, W * 0.66)))
  const tip = useTooltip()
  const [hover, setHover] = useState(null)
  const rankOf = useMemo(() => {
    const m = new Map()
    clusters.forEach((c) => c.members.forEach((id) => m.set(id, c.rank)))
    return m
  }, [clusters])

  const graph = useMemo(() => layoutClusters(network, clusters, rankOf, W, H), [network, clusters, rankOf, W, H])

  if (!graph) return <div ref={wrap} className="viz"><div className="empty">{t('Clusters appear once enough outlets have 10+ articles.')}</div></div>
  const focus = hover || (highlight != null ? `c:${highlight}` : null)
  const active = (n) => !focus || (focus.startsWith('c:') ? n.rank === +focus.slice(2) : n.id === focus)
  const name = (c) => (lang === 'ar' && c.name_ar ? c.name_ar : c.name)
  const clusterOf = (n) => clusters.find((c) => c.rank === n.rank)
  return (
    <div ref={wrap} className="viz" onMouseLeave={() => { tip.hide(); setHover(null) }}>
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={t('Outlets positioned by coverage similarity, coloured and labelled by cluster')}>
        <defs>
          <marker id="rp-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" fill="var(--ink-2)" />
          </marker>
        </defs>
        {showSimilarity && graph.sims.map((l, i) => <line key={i} x1={l.s.x} y1={l.s.y} x2={l.t.x} y2={l.t.y} stroke="var(--grid)" strokeWidth={1} />)}
        {showReprints && graph.reprints.map((l, i) => {
          const dx = l.t.x - l.s.x, dy = l.t.y - l.s.y, len = Math.hypot(dx, dy) || 1, rt = graph.r(l.t.articles) + 3
          const on = !focus || active(l.s) || active(l.t)
          return <line key={i} x1={l.s.x} y1={l.s.y} x2={l.t.x - (dx / len) * rt} y2={l.t.y - (dy / len) * rt}
            stroke="var(--ink-2)" strokeWidth={Math.min(3.5, 0.8 + Math.log2(l.weight))} strokeOpacity={on ? 0.6 : 0.06} markerEnd="url(#rp-arrow)" />
        })}
        {graph.nodes.map((n) => (
          <g key={n.id} transform={`translate(${n.x},${n.y})`} opacity={active(n) ? 1 : 0.18} style={{ cursor: 'pointer' }}
            onMouseMove={(e) => { setHover(n.id); tip.show(e, <div><b dir="auto">{n.name}</b> <span className="muted">{n.domain}</span>
              <div>{t('{n} articles (12 weeks)', { n: fmt(n.articles) })}</div>
              <div className="small">{(clusterOf(n) && name(clusterOf(n))) || t('Other clusters')}</div></div>, wrap.current, n.id) }}
            onClick={() => onSelectOutlet?.(n)}>
            <circle r={graph.r(n.articles) + 4} fill="transparent" />
            <circle r={graph.r(n.articles)} fill={clusterColor(n.rank)} stroke="var(--surface)" strokeWidth={2} />
            {graph.r(n.articles) > 10 && <text y={graph.r(n.articles) + 12} textAnchor="middle"
              style={{ fontSize: 11, fill: 'var(--ink)', paintOrder: 'stroke', stroke: 'var(--surface)', strokeWidth: 3 }}>{n.name}</text>}
          </g>))}
        {graph.tags.map(({ c, x, y }) => {
          const label = name(c)
          const w = Math.min(220, 14 + label.length * 6.4)
          return (
            <g key={c.id} transform={`translate(${x - w / 2},${y - 10})`} style={{ cursor: 'pointer' }}
              onMouseEnter={() => setHighlight?.(c.rank)} onMouseLeave={() => setHighlight?.(null)}>
              <rect width={w} height={20} rx={4} fill={clusterColor(c.rank)} />
              <text x={w / 2} y={14} textAnchor="middle" style={{ fontSize: 11, fontWeight: 600, fill: c.rank === 1 || c.rank === 3 ? 'var(--ink)' : '#fff' }}>
                {label.length > 32 ? label.slice(0, 31) + '…' : label}</text>
            </g>)
        })}
      </svg>
      {tip.node}
    </div>
  )
}

// A row lights its cluster up on the map while hovered or focused (Tab reaches every row); Enter, Space or
// a click opens it (onOpen: the Outlets page switches to the outlet map with that cluster in focus).
export function ClusterLegendTable({ clusters, themes, highlight, setHighlight, lang = 'en', onOpen }) {
  const tname = new Map(themes.map((t) => [t.id, lang === 'ar' ? t.name_ar : t.name_en]))
  const named = clusters.filter((c) => c.rank < CLUSTER_SLOTS.length)
  const other = clusters.filter((c) => c.rank >= CLUSTER_SLOTS.length)
  const row = (c, label, color, extra) => (
    <tr key={label} tabIndex={c ? 0 : undefined} style={{ cursor: c ? 'pointer' : undefined, ...(highlight != null && c?.rank === highlight ? { background: 'var(--surface-2)' } : {}) }}
      onMouseEnter={() => setHighlight?.(c?.rank ?? null)} onMouseLeave={() => setHighlight?.(null)}
      onFocus={() => setHighlight?.(c?.rank ?? null)} onBlur={() => setHighlight?.(null)}
      onClick={() => c && onOpen?.(c.rank)}
      onKeyDown={(e) => { if (c && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); onOpen?.(c.rank) } }}>
      <td><span className="sw" style={{ display: 'inline-block', width: 12, height: 12, borderRadius: 3, background: color, verticalAlign: -2, marginInlineEnd: 6 }} /><b>{label}</b>
        {extra}</td>
      <td className="num">{c ? c.outlets : d3sum(other, (x) => x.outlets)}</td>
      <td className="num">{fmt(c ? c.articles : d3sum(other, (x) => x.articles))}</td>
      <td className="num">{Math.round((c ? c.share : d3sum(other, (x) => x.share)) * 100)}%</td>
    </tr>)
  const comma = isAr() ? '، ' : ', '
  return (
    <table className="data">
      <thead><tr><th>{t('Cluster')}</th><th className="num">{t('Outlets')}</th><th className="num">{t('Articles')}</th><th className="num">{t('Share')}</th></tr></thead>
      <tbody>
        {named.map((c) => row(c, lang === 'ar' && c.name_ar ? c.name_ar : c.name, clusterColor(c.rank), (
          <div className="small muted">{c.tags.map(tagText).join(' · ')} · {t('over-covers {themes}', { themes: c.themes.filter((th) => th.lift >= 1.15).slice(0, 2).map((th) => `${tname.get(th.theme_id)} (×${num(th.lift)})`).join(comma) || '—' })}
            <div>{t('e.g. {outlets}', { outlets: c.top_outlets.slice(0, 3).join(comma) })}</div></div>)))}
        {other.length > 0 && row(null, t('Other clusters ({n})', { n: other.length }), 'var(--cat-unknown)', null)}
      </tbody>
    </table>
  )
}

// Cluster × district: share of each cluster's articles naming each district. Empty = no cluster covers it.
export function ClusterDistrictTable({ clusters, districts, regions, lang = 'en', highlight, onSelectDistrict }) {
  const named = clusters.filter((c) => c.rank < CLUSTER_SLOTS.length)
  const macro = new Map(regions.filter((r) => r.level === 'macro').map((r) => [r.id, r]))
  const max = d3max(named.flatMap((c) => Object.values(c.district_share))) || 0.01
  const shade = (v) => {
    if (!v) return null
    const i = Math.min(5, 1 + Math.floor((v / max) * 5))
    return `var(--cov-${Math.min(i, 5)})`
  }
  const covered = (d) => named.some((c) => c.district_share[d.id] > 0) || clusters.some((c) => c.district_share[d.id] > 0)
  return (
    <div className="scroll" style={{ maxHeight: 620 }}>
      <table className="data">
        <thead><tr><th>{t('District')}</th>{named.map((c) => (
          <th key={c.id} className="num" style={{ minWidth: 90, maxWidth: 150, whiteSpace: 'normal', verticalAlign: 'bottom', background: highlight === c.rank ? 'var(--surface-2)' : undefined }}>
            <span className="sw" style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 2, background: clusterColor(c.rank), marginInlineEnd: 4 }} />
            <span style={{ fontSize: 11.5, fontWeight: 600 }}>{lang === 'ar' && c.name_ar ? c.name_ar : c.name}</span></th>))}</tr></thead>
        <tbody>{districts.map((d, i) => {
          const newMacro = i === 0 || districts[i - 1].parent_id !== d.parent_id
          return (
            <Fragment key={d.id}>{newMacro && <tr><td colSpan={named.length + 1} className="small muted" style={{ fontWeight: 600, paddingTop: 10 }}>{pick(macro.get(d.parent_id), 'name')}</td></tr>}
              <tr style={{ cursor: 'pointer' }} tabIndex={0} onClick={() => onSelectDistrict?.(d.id)}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelectDistrict?.(d.id) } }}>
                <td>{lang === 'ar' ? d.name_ar : d.name_en}{!covered(d) && <span className="pill flag" style={{ marginInlineStart: 6 }}>{t('no cluster covers it')}</span>}</td>
                {named.map((c) => {
                  const v = c.district_share[d.id] || 0
                  const bg = shade(v)
                  return <td key={c.id} className="num" style={{ background: bg || undefined, color: v / max > 0.6 ? '#fff' : undefined }}
                    title={t('{cluster}: {pct}% of its articles name {district}', { cluster: lang === 'ar' && c.name_ar ? c.name_ar : c.name, pct: num(v * 100, 1), district: lang === 'ar' ? d.name_ar || d.name_en : d.name_en })}>{v ? `${num(v * 100, v < 0.01 ? 1 : 0)}%` : <span className="muted">·</span>}</td>
                })}
              </tr></Fragment>)
        })}</tbody>
      </table>
    </div>
  )
}
