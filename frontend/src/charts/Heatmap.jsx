// Theme × region grid. Fill = gap (red ramp); hatched = insufficient evidence;
// each cell also prints the raw counts so the score is never a black box.
import * as d3 from 'd3'
import { useRef } from 'react'
import { INFO_FLAGS, fmt, gapFill, gapLabel, flagText } from './scales'
import { HatchDefs, useSize, useTooltip } from './util'

export default function Heatmap({ themes, regions, cells, onSelect, svgRef, unit = 'need', lang = 'en', feedback = {} }) {
  const wrap = useRef(null)
  const W = useSize(wrap, 700)
  const tip = useTooltip()
  const left = Math.min(190, W * 0.34)
  const top = 34
  const cw = Math.max(44, (W - left) / Math.max(regions.length, 1))
  const ch = 40
  const H = top + ch * themes.length + 4
  const byKey = new Map(cells.map((c) => [`${c.theme_id}:${c.region_id}`, c]))
  const nm = (o) => (lang === 'ar' ? o.name_ar : o.name_en) || o.name_en
  return (
    <div ref={wrap} className="viz" onMouseLeave={tip.hide}>
      <svg ref={svgRef} viewBox={`0 0 ${Math.max(W, left + cw * regions.length)} ${H}`} role="img" aria-label="Gap by theme and region">
        <HatchDefs id="hm-hatch" />
        {regions.map((r, j) => (
          <text key={r.id} x={left + j * cw + cw / 2} y={top - 10} textAnchor="middle" style={{ fontSize: 11, fontWeight: 600 }}>
            {nm(r).length > 14 ? nm(r).slice(0, 13) + '…' : nm(r)}</text>))}
        {themes.map((t, i) => (
          <g key={t.id} transform={`translate(0,${top + i * ch})`}>
            <text x={left - 10} y={ch / 2 + 4} textAnchor="end" style={{ fontSize: 12, fill: 'var(--ink)' }}>{nm(t)}</text>
            {regions.map((r, j) => {
              const c = byKey.get(`${t.id}:${r.id}`)
              const fill = gapFill(c) || (c ? 'url(#hm-hatch)' : 'var(--surface-2)')
              const fb = feedback[`${t.id}:${r.id}`]
              const dark = c && !c.insufficient && c.gap >= 1.0
              return (
                <g key={r.id} transform={`translate(${left + j * cw},0)`} style={{ cursor: c ? 'pointer' : 'default' }}
                  onClick={() => c && onSelect?.(t.id, r.id)}
                  onMouseMove={(e) => tip.show(e, c ? (
                    <div><b>{t.name_en} · {r.name_en}</b>
                      <div>{fmt(c.coverage)} articles · {fmt(c.need)} {unit}</div>
                      <div>{gapLabel(c.insufficient ? null : c.gap)}</div>
                      {(c.flags || []).map((f) => <div key={f} className={INFO_FLAGS.has(f) ? "pill" : "pill flag"} style={{ marginTop: 3 }}>{flagText(f)}</div>)}
                      {fb && <div className="small muted" style={{ marginTop: 4 }}>Team: {Object.entries(fb).map(([k, v]) => `${v} ${k.replace('_', ' ')}`).join(', ')}</div>}
                    </div>) : <div>No data for this cell</div>, wrap.current)}>
                  <rect x={1} y={1} width={cw - 2} height={ch - 2} rx={4} fill={fill} />
                  {c && <text x={cw / 2} y={ch / 2 + 4} textAnchor="middle" className="num"
                    style={{ fontSize: 11, fill: dark ? '#fff' : 'var(--ink-2)' }}>{fmt(c.coverage)}</text>}
                  {fb?.real > 0 && <circle cx={cw - 7} cy={7} r={3} fill="var(--ink)" stroke="var(--surface)" strokeWidth={1.5} />}
                </g>)
            })}
          </g>))}
      </svg>
      {tip.node}
      <div className="legend" style={{ marginTop: 8 }}>
        <span>Under-coverage <span className="ramp">{[1, 2, 3, 4, 5, 6].map((i) => <span key={i} style={{ background: `var(--gap-${i})` }} />)}</span></span>
        <span><svg width="14" height="12" style={{ verticalAlign: -2, marginRight: 5 }}><rect width="14" height="12" fill="url(#hm-hatch)" rx="2" /></svg>insufficient evidence</span>
        <span>Number = monitored articles (4 weeks)</span>
        <span><svg width="10" height="10" style={{ verticalAlign: -1, marginRight: 4 }}><circle cx="5" cy="5" r="3" fill="var(--ink)" /></svg>a journalist marked it a real gap</span>
      </div>
    </div>
  )
}

// Need and coverage share one axis by indexing each to its own mean (=100): no dual axis.
export function TrendMultiples({ themes, series, onSelect, lang = 'en', unit }) {
  const wrap = useRef(null)
  const W = useSize(wrap, 900)
  const cols = W < 560 ? 1 : W < 900 ? 2 : 3
  const cw = Math.floor(W / cols) - 12
  const ch = 132
  const tip = useTooltip()
  return (
    <div ref={wrap} className="viz" onMouseLeave={tip.hide}>
      <div style={{ display: 'grid', gridTemplateColumns: `repeat(${cols}, minmax(0,1fr))`, gap: 12 }}>
        {themes.map((t) => {
          const rows = (series[t.id] || []).filter((r) => !r.breakdown?.partial_window).slice(-52)
          const idx = (k) => { const m = d3.mean(rows, (r) => r[k]) || 0; return rows.map((r) => (m ? (r[k] / m) * 100 : 0)) }
          const need = idx('need'), cov = idx('coverage')
          const x = d3.scalePoint().domain(rows.map((r) => r.week)).range([30, cw - 8])
          const ymax = Math.max(160, d3.max([...need, ...cov]) || 0)
          const y = d3.scaleLinear().domain([0, ymax]).range([ch - 22, 8]).nice()
          const line = (vals) => d3.line().x((_, i) => x(rows[i].week)).y((v) => y(v)).curve(d3.curveMonotoneX)(vals)
          const last = rows[rows.length - 1]
          return (
            <div key={t.id} className="card" style={{ padding: 10, cursor: 'pointer' }} onClick={() => onSelect?.(t.id)}>
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <b style={{ fontSize: 13 }}>{lang === 'ar' ? t.name_ar : t.name_en}</b>
                <span className="small muted">{last ? (last.insufficient ? 'insufficient' : last.gap >= 0.4 ? <span className="pill flag">gap</span> : 'ok') : ''}</span>
              </div>
              {rows.length < 2 ? <div className="empty small">Not enough weeks yet</div> : (
                <svg viewBox={`0 0 ${cw} ${ch}`} style={{ width: '100%' }}
                  onMouseMove={(e) => {
                    const box = e.currentTarget.getBoundingClientRect()
                    const px = ((e.clientX - box.left) / box.width) * cw
                    const i = d3.minIndex(rows, (r) => Math.abs(x(r.week) - px))
                    const r = rows[i]
                    tip.show(e, <div><b>Week of {r.week}</b><div>{fmt(r.coverage)} articles · {fmt(r.need)} {unit}</div>
                      <div className="small muted">4-week window</div></div>, wrap.current)
                  }}>
                  {y.ticks(3).map((v) => <g key={v}><line x1={30} x2={cw - 8} y1={y(v)} y2={y(v)} stroke="var(--grid)" />
                    <text x={26} y={y(v) + 3} textAnchor="end" style={{ fontSize: 9 }}>{v}</text></g>)}
                  <path d={line(need)} fill="none" stroke="var(--ink-2)" strokeWidth={2} strokeDasharray="0" />
                  <path d={line(cov)} fill="none" stroke="var(--accent)" strokeWidth={2} />
                  <circle cx={x(last.week)} cy={y(cov[cov.length - 1])} r={4} fill="var(--accent)" stroke="var(--surface)" strokeWidth={2} />
                  <circle cx={x(last.week)} cy={y(need[need.length - 1])} r={4} fill="var(--ink-2)" stroke="var(--surface)" strokeWidth={2} />
                  <text x={30} y={ch - 6} style={{ fontSize: 9 }}>{rows[0].week}</text>
                  <text x={cw - 8} y={ch - 6} textAnchor="end" style={{ fontSize: 9 }}>{last.week}</text>
                </svg>)}
            </div>)
        })}
      </div>
      {tip.node}
      <div className="legend" style={{ marginTop: 10 }}>
        <span><span className="sw" style={{ background: 'var(--ink-2)', height: 3 }} />Need ({unit})</span>
        <span><span className="sw" style={{ background: 'var(--accent)', height: 3 }} />Monitored coverage</span>
        <span className="muted">Last 52 weeks. Both indexed to their own average = 100, so they share one axis.</span>
      </div>
    </div>
  )
}
