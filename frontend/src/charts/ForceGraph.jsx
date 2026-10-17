// Outlet similarity network (who covers the same mix of themes) + syndication arrows
// (who reprints whom). Layout runs once per data change, then is static (no jiggling).
import * as d3 from 'd3'
import { useMemo, useRef, useState } from 'react'
import { DIMENSIONS, categoryColor, categoryOf, fmt } from './scales'
import { useSize, useTooltip } from './util'
import { pick, t } from '../i18n'

export default function ForceGraph({ network, colorBy, show = { similar: true, syndication: true }, onSelectOutlet, svgRef, maxNodes = 60, minReprints = 2 }) {
  const wrap = useRef(null)
  const W = useSize(wrap, 800)
  const H = Math.round(Math.min(620, Math.max(380, W * 0.62)))
  const tip = useTooltip()
  const [hover, setHover] = useState(null)

  const graph = useMemo(() => {
    if (!network) return null
    // Readability cap: the largest outlets only (the table below lists everyone).
    const outlets = network.nodes.filter((n) => n.type === 'outlet').sort((a, b) => b.articles - a.articles).slice(0, maxNodes)
    const ids = new Set(outlets.map((o) => o.id))
    const links = network.edges.filter((e) => ((e.kind === 'outlet_outlet' && show.similar) || (e.kind === 'syndication' && show.syndication && e.weight >= minReprints))
      && ids.has(e.source) && ids.has(e.target)).map((e) => ({ ...e }))
    const linked = new Set(links.flatMap((l) => [l.source, l.target]))
    const nodes = outlets.filter((o) => linked.has(o.id)).map((o) => ({ ...o }))
    const keep = new Set(nodes.map((n) => n.id))
    const ls = links.filter((l) => keep.has(l.source) && keep.has(l.target))
    const r = d3.scaleSqrt().domain([0, d3.max(nodes, (n) => n.articles) || 1]).range([4, 18])
    const sim = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(ls).id((d) => d.id).distance((l) => l.kind === 'syndication' ? 60 : 90 - 40 * l.weight).strength((l) => l.kind === 'syndication' ? 0.3 : l.weight * 0.6))
      .force('charge', d3.forceManyBody().strength(-110))
      .force('collide', d3.forceCollide((d) => r(d.articles) + 4))
      .force('x', d3.forceX(W / 2).strength(0.05)).force('y', d3.forceY(H / 2).strength(0.07))
      .stop()
    for (let i = 0; i < 300; i++) sim.tick()
    // fit to the frame (scale, don't clamp — clamping piles nodes on the border)
    const [x0, x1] = d3.extent(nodes, (n) => n.x), [y0, y1] = d3.extent(nodes, (n) => n.y)
    const pad = 40
    const k = Math.min((W - 2 * pad) / Math.max(1, x1 - x0), (H - 2 * pad) / Math.max(1, y1 - y0), 1.6)
    nodes.forEach((n) => { n.x = pad + (n.x - x0) * k + ((W - 2 * pad) - (x1 - x0) * k) / 2; n.y = pad + (n.y - y0) * k + ((H - 2 * pad) - (y1 - y0) * k) / 2 })
    // community hulls
    const comms = d3.groups(nodes.filter((n) => n.community != null), (n) => n.community).filter(([, g]) => g.length >= 3)
    return { nodes, links: ls, r, comms }
  }, [network, W, H, show.similar, show.syndication, maxNodes, minReprints])

  if (!graph) return <div ref={wrap} className="viz"><div className="empty">{t('Loading…')}</div></div>
  if (!graph.nodes.length) return <div ref={wrap} className="viz"><div className="empty">{t('Not enough shared coverage yet to draw a network.')}</div></div>
  const nb = hover ? new Set(graph.links.filter((l) => l.source.id === hover || l.target.id === hover).flatMap((l) => [l.source.id, l.target.id])) : null
  return (
    <div ref={wrap} className="viz" onMouseLeave={() => { tip.hide(); setHover(null) }}>
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={t('Network of outlets linked by similar coverage and reprinted headlines')}>
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" fill="var(--ink-2)" />
          </marker>
        </defs>
        {graph.comms.map(([c, g]) => {
          const hull = d3.polygonHull(g.flatMap((n) => [[n.x - 10, n.y - 10], [n.x + 10, n.y + 10], [n.x - 10, n.y + 10], [n.x + 10, n.y - 10]]))
          return hull && <path key={c} d={`M${hull.join('L')}Z`} fill="var(--surface-2)" stroke="var(--surface-2)" strokeLinejoin="round" strokeWidth={14} opacity={0.8} />
        })}
        {graph.links.map((l, i) => {
          const on = !hover || l.source.id === hover || l.target.id === hover
          if (l.kind === 'syndication') {
            const dx = l.target.x - l.source.x, dy = l.target.y - l.source.y, len = Math.hypot(dx, dy) || 1
            const rt = graph.r(l.target.articles) + 3
            return <line key={i} x1={l.source.x} y1={l.source.y} x2={l.target.x - (dx / len) * rt} y2={l.target.y - (dy / len) * rt}
              stroke="var(--ink-2)" strokeWidth={Math.min(4, 1 + Math.log2(l.weight))} strokeOpacity={on ? 0.75 : 0.08} markerEnd="url(#arrow)" />
          }
          return <line key={i} x1={l.source.x} y1={l.source.y} x2={l.target.x} y2={l.target.y} stroke="var(--axis)"
            strokeWidth={1 + l.weight * 2} strokeOpacity={on ? 0.8 : 0.1} />
        })}
        {graph.nodes.map((n) => (
          <g key={n.id} transform={`translate(${n.x},${n.y})`} style={{ cursor: 'pointer' }} opacity={nb && !nb.has(n.id) ? 0.25 : 1}
            onMouseMove={(e) => {
              setHover(n.id)
              tip.show(e, <div><b dir="auto">{pick(n)}</b> <span className="muted">{n.domain}</span>
                <div>{t('{count} articles in window', { count: fmt(n.articles) })}</div>
                <div className="small">{t(DIMENSIONS[colorBy].label)}: {t(DIMENSIONS[colorBy].values[categoryOf(n, colorBy)])}</div>
                {n.community != null && <div className="small muted">{t('Coverage cluster {n}', { n: n.community + 1 })}</div>}</div>, wrap.current)
            }}
            onClick={() => onSelectOutlet?.(n)}>
            <circle r={graph.r(n.articles) + 5} fill="transparent" />
            <circle r={graph.r(n.articles)} fill={categoryColor(colorBy, categoryOf(n, colorBy))} stroke="var(--surface)" strokeWidth={2} />
            {(graph.r(n.articles) > 9 || hover === n.id) && <text y={graph.r(n.articles) + 12} textAnchor="middle"
              style={{ fontSize: 10.5, fill: 'var(--ink)', paintOrder: 'stroke', stroke: 'var(--surface)', strokeWidth: 3 }}>{pick(n)}</text>}
          </g>))}
      </svg>
      {tip.node}
    </div>
  )
}
