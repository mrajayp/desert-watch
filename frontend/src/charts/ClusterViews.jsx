// Two companions to the outlet-level cluster map:
//  * ClusterSummary   - one circle per cluster (area = articles), arrows = reprint flow between
//                       clusters. The default, readable-at-a-glance view.
//  * ClusterMultiples - the outlet map repeated for consecutive 4-week periods with the outlet set
//                       and positions held fixed; node size = that period's articles. Differences
//                       between panels are changes in coverage, not in what was collected.
import * as d3 from 'd3'
import { useMemo, useRef, useState } from 'react'
import { CLUSTER_SLOTS, clusterColor, layoutClusters } from './ClusterMap'
import { fmt } from './scales'
import { useSize, useTooltip } from './util'

function rankMap(clusters) {
  const m = new Map()
  clusters.forEach((c) => c.members.forEach((id) => m.set(id, c.rank)))
  return m
}

// ---------------------------------------------------------------- summary
export function ClusterSummary({ network, clusters, themes, lang = 'en', onOpenCluster, svgRef }) {
  const wrap = useRef(null)
  const W = useSize(wrap, 800)
  const H = Math.round(Math.min(520, Math.max(360, W * 0.56)))
  const tip = useTooltip()
  const [hover, setHover] = useState(null)
  const tname = useMemo(() => new Map(themes.map((t) => [t.id, lang === 'ar' ? t.name_ar : t.name_en])), [themes, lang])

  const layout = useMemo(() => {
    if (!network || !clusters.length) return null
    const named = clusters.filter((c) => c.rank < CLUSTER_SLOTS.length)
    const other = clusters.filter((c) => c.rank >= CLUSTER_SLOTS.length)
    const groups = [...named.map((c) => ({ key: c.rank, c, articles: c.articles, outlets: c.outlets, members: new Set(c.members) }))]
    if (other.length) groups.push({ key: 'other', c: null, articles: d3.sum(other, (c) => c.articles), outlets: d3.sum(other, (c) => c.outlets), members: new Set(other.flatMap((c) => c.members)) })
    const groupOf = new Map()
    groups.forEach((g) => g.members.forEach((m) => groupOf.set(m, g.key)))
    // reprint flow between clusters (and within)
    const flow = new Map()
    const within = new Map()
    for (const e of network.edges) {
      if (e.kind !== 'syndication') continue
      const a = groupOf.get(e.source), b = groupOf.get(e.target)
      if (a == null || b == null) continue
      if (a === b) within.set(a, (within.get(a) || 0) + e.weight)
      else flow.set(`${a}|${b}`, (flow.get(`${a}|${b}`) || 0) + e.weight)
    }
    const maxR = Math.min(W, H) * 0.2
    const r = d3.scaleSqrt().domain([0, d3.max(groups, (g) => g.articles) || 1]).range([0, maxR])
    const nodes = groups.map((g, i) => ({ ...g, r: Math.max(18, r(g.articles)), x: W / 2 + Math.cos(i * 2.4) * 60, y: H / 2 + Math.sin(i * 2.4) * 40 }))
    const sim = d3.forceSimulation(nodes).force('collide', d3.forceCollide((d) => d.r + 46)).force('x', d3.forceX(W / 2).strength(0.06))
      .force('y', d3.forceY(H / 2).strength(0.1)).stop()
    for (let i = 0; i < 300; i++) sim.tick()
    nodes.forEach((n) => { n.x = Math.max(n.r + 10, Math.min(W - n.r - 10, n.x)); n.y = Math.max(n.r + 10, Math.min(H - n.r - 46, n.y)) })
    const byKey = new Map(nodes.map((n) => [n.key, n]))
    const links = [...flow.entries()].map(([k, w]) => { const [a, b] = k.split('|'); return { s: byKey.get(isNaN(a) ? a : +a), t: byKey.get(isNaN(b) ? b : +b), w } })
      .filter((l) => l.s && l.t && l.w >= 3)
      .sort((a, b) => b.w - a.w).slice(0, 8)  // strongest flows only; the outlet view has the rest
    const wScale = d3.scaleSqrt().domain([3, d3.max(links, (l) => l.w) || 3]).range([1, 4.5])
    return { nodes, links, within, wScale }
  }, [network, clusters, W, H])

  if (!layout) return <div ref={wrap} className="viz"><div className="empty">Clusters appear once enough outlets have 10+ articles.</div></div>
  const total = d3.sum(layout.nodes, (n) => n.articles) || 1
  const label = (n) => (n.c ? (lang === 'ar' && n.c.name_ar ? n.c.name_ar : n.c.name) : 'Other clusters')
  const arrow = (l) => {
    // curved arrow from edge of s to edge of t
    const dx = l.t.x - l.s.x, dy = l.t.y - l.s.y, len = Math.hypot(dx, dy) || 1
    const ux = dx / len, uy = dy / len
    const sx = l.s.x + ux * (l.s.r + 4), sy = l.s.y + uy * (l.s.r + 4)
    const tx = l.t.x - ux * (l.t.r + 8), ty = l.t.y - uy * (l.t.r + 8)
    const mx = (sx + tx) / 2 - uy * len * 0.12, my = (sy + ty) / 2 + ux * len * 0.12
    return `M${sx},${sy} Q${mx},${my} ${tx},${ty}`
  }
  return (
    <div ref={wrap} className="viz" onMouseLeave={() => { tip.hide(); setHover(null) }}>
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Coverage clusters as circles sized by article volume, with reprint flows between them">
        <defs>
          <marker id="cs-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="9" markerHeight="9" markerUnits="userSpaceOnUse" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" fill="var(--ink-2)" />
          </marker>
        </defs>
        {layout.links.map((l, i) => {
          const on = hover == null || l.s.key === hover || l.t.key === hover
          return <path key={i} d={arrow(l)} fill="none" stroke="var(--ink-2)" strokeWidth={layout.wScale(l.w)} strokeOpacity={on ? 0.45 : 0.06}
            markerEnd="url(#cs-arrow)" onMouseMove={(e) => tip.show(e, <div><b>{label(l.s)} → {label(l.t)}</b><div>{l.w} near-identical headlines published later by the second cluster</div></div>, wrap.current)} />
        })}
        {layout.nodes.map((n) => {
          const top = n.c ? n.c.themes.filter((t) => t.lift >= 1.15).slice(0, 2) : []
          const on = hover == null || hover === n.key
          return (
            <g key={n.key} transform={`translate(${n.x},${n.y})`} style={{ cursor: n.c ? 'pointer' : 'default' }} opacity={on ? 1 : 0.35}
              onMouseMove={(e) => { setHover(n.key); tip.show(e, (
                <div><b>{label(n)}</b>
                  <div>{n.outlets} outlets · {fmt(n.articles)} articles ({Math.round((n.articles / total) * 100)}%)</div>
                  {n.c && <div className="small">{n.c.tags.join(' · ')}</div>}
                  {top.map((t) => <div key={t.theme_id} className="small">over-covers {tname.get(t.theme_id)} ×{t.lift}</div>)}
                  {layout.within.get(n.key) ? <div className="small muted">{layout.within.get(n.key)} reprints inside the cluster</div> : null}
                  {n.c && <div className="small muted">e.g. {n.c.top_outlets.slice(0, 3).join(', ')}</div>}
                </div>), wrap.current) }}
              onClick={() => n.c && onOpenCluster?.(n.c.rank)}>
              <circle r={n.r} fill={n.c ? clusterColor(n.c.rank) : 'var(--cat-unknown)'} fillOpacity={0.9} stroke="var(--surface)" strokeWidth={2} />
              <text y={4} textAnchor="middle" className="num" style={{ fontSize: Math.max(11, Math.min(20, n.r / 3)), fontWeight: 600, fill: n.c && (n.c.rank === 1 || n.c.rank === 3) ? 'var(--ink)' : n.c ? '#fff' : 'var(--ink)' }}>
                {Math.round((n.articles / total) * 100)}%</text>
              <text y={n.r + 15} textAnchor="middle" style={{ fontSize: 12, fontWeight: 600, fill: 'var(--ink)', paintOrder: 'stroke', stroke: 'var(--surface)', strokeWidth: 3 }}>
                {label(n).length > 34 ? label(n).slice(0, 33) + '…' : label(n)}</text>
              <text y={n.r + 29} textAnchor="middle" style={{ fontSize: 10.5, fill: 'var(--ink-2)', paintOrder: 'stroke', stroke: 'var(--surface)', strokeWidth: 3 }}>
                {n.outlets} outlets{n.c ? ` · ${n.c.tags[0]}` : ''}</text>
            </g>)
        })}
      </svg>
      {tip.node}
      <div className="legend">
        <span>Circle area = articles (12 weeks); number = share of all clustered coverage</span>
        <span><svg width="26" height="10" style={{ verticalAlign: -1, marginRight: 4 }}><line x1="1" y1="5" x2="20" y2="5" stroke="var(--ink-2)" strokeWidth="2" /><path d="M18,1 L25,5 L18,9 z" fill="var(--ink-2)" /></svg>reprint flow (8 strongest, 3+ headlines): the arrowhead cluster republished the other’s headlines</span>
        <span className="muted">Click a cluster to see its outlets.</span>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------- small multiples
export function ClusterMultiples({ network, clusters, periods, lang = 'en', svgRef }) {
  const wrap = useRef(null)
  const W = useSize(wrap, 900)
  const tip = useTooltip()
  const n = periods?.periods?.length || 0
  const cols = W < 560 ? 1 : Math.min(n || 3, W < 900 ? 2 : 3)
  const gap = 14
  const pw = Math.floor((W - gap * (cols - 1)) / Math.max(cols, 1))
  const ph = Math.round(pw * 0.72)
  const rankOf = useMemo(() => rankMap(clusters), [clusters])
  // one layout, reused by every panel
  const base = useMemo(() => layoutClusters(network, clusters, rankOf, 1000, 720), [network, clusters, rankOf])
  const idByCluster = useMemo(() => new Map(clusters.map((c) => [c.id, c])), [clusters])
  if (!base || !n) return <div ref={wrap} className="viz"><div className="empty">Small multiples need at least one full 4-week period of network data.</div></div>
  const rows = Math.ceil(n / cols)
  const H = rows * (ph + 52) + 4
  const maxN = d3.max(Object.values(periods.outlets).flat()) || 1
  const r = d3.scaleSqrt().domain([0, maxN]).range([0, Math.max(12, pw / 22)])
  const sx = pw / 1000, sy = ph / 720
  return (
    <div ref={wrap} className="viz" onMouseLeave={tip.hide}>
      <div className="legend" style={{ marginBottom: 4 }}>
        {clusters.filter((c) => c.rank < CLUSTER_SLOTS.length).map((c) => (
          <span key={c.id}><span className="sw" style={{ background: clusterColor(c.rank), borderRadius: '50%' }} />{lang === 'ar' && c.name_ar ? c.name_ar : c.name}</span>))}
        {clusters.some((c) => c.rank >= CLUSTER_SLOTS.length) && <span><span className="sw" style={{ background: 'var(--cat-unknown)', borderRadius: '50%' }} />Other clusters</span>}
      </div>
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Coverage clusters in consecutive four-week periods">
        {periods.periods.map((p, i) => {
          const ox = (i % cols) * (pw + gap), oy = Math.floor(i / cols) * (ph + 52)
          const totals = Object.entries(periods.clusters).map(([cid, v]) => ({ c: idByCluster.get(+cid), n: v.articles[i] }))
          const sum = d3.sum(totals, (t) => t.n) || 1
          const shares = totals.filter((t) => t.c).sort((a, b) => a.c.rank - b.c.rank)
          let acc = 0
          return (
            <g key={p.start} transform={`translate(${ox},${oy})`}>
              <rect width={pw} height={ph + 44} rx={6} fill="var(--surface)" stroke="var(--grid)" />
              <text x={10} y={18} style={{ fontSize: 12, fontWeight: 600, fill: 'var(--ink)' }}>{p.start} → {p.end}</text>
              <text x={pw - 10} y={18} textAnchor="end" className="num" style={{ fontSize: 11 }}>{fmt(sum)} articles</text>
              <g transform="translate(0,22)">
                {base.nodes.map((nd) => {
                  const v = periods.outlets[nd.id]?.[i] || 0
                  return v > 0 ? (
                    <circle key={nd.id} cx={nd.x * sx} cy={nd.y * sy} r={Math.max(2.4, r(v))} fill={clusterColor(nd.rank)} stroke="var(--surface)" strokeWidth={1}
                      onMouseMove={(e) => tip.show(e, <div><b>{nd.name}</b><div>{fmt(v)} articles, {p.start} → {p.end}</div></div>, wrap.current)} />
                  ) : <circle key={nd.id} cx={nd.x * sx} cy={nd.y * sy} r={1.4} fill="none" stroke="var(--axis)" strokeWidth={0.8} />
                })}
              </g>
              {/* cluster share bar for this period */}
              <g transform={`translate(10,${ph + 28})`}>
                {shares.map((t) => {
                  const w = ((t.n / sum) * (pw - 20))
                  const el = <rect key={t.c.id} x={acc} y={0} width={Math.max(0, w - 1.5)} height={8} rx={2} fill={clusterColor(t.c.rank)}
                    onMouseMove={(e) => tip.show(e, <div><b>{lang === 'ar' && t.c.name_ar ? t.c.name_ar : t.c.name}</b><div>{fmt(t.n)} articles ({Math.round((t.n / sum) * 100)}%)</div></div>, wrap.current)} />
                  acc += w
                  return el
                })}
              </g>
            </g>)
        })}
      </svg>
      {tip.node}
      <div className="legend">
        <span>Same outlets, same positions in every panel; dot area = that outlet’s articles in the period; hollow = silent that period.</span>
        <span>Bar = each cluster’s share of the period’s coverage.</span>
      </div>
    </div>
  )
}
