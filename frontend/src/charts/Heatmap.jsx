// Theme × region grid. Fill = gap (red ramp); hatched = insufficient evidence;
// each cell also prints the raw counts so the score is never a black box.
import { useRef } from 'react'
import { INFO_FLAGS, fmt, gapFill, gapLabel, flagText } from './scales'
import { HatchDefs, fitLabel, groupedRows, themeLabel, useSize, useTooltip } from './util'

export default function Heatmap({ themes, regions, cells, onSelect, svgRef, unit = 'need', lang = 'en', feedback = {} }) {
  const wrap = useRef(null)
  const W = useSize(wrap, 700)
  const tip = useTooltip()
  const left = Math.min(240, Math.max(120, W * 0.3))
  const top = 34
  const cw = Math.max(44, (W - left) / Math.max(regions.length, 1))
  const ch = 40
  const hh = 26 // group heading row
  const rows = groupedRows(themes)
  const ys = []
  let yy = top
  rows.forEach((r) => { ys.push(yy); yy += r.header ? hh : ch })
  const H = yy + 4
  const byKey = new Map(cells.map((c) => [`${c.theme_id}:${c.region_id}`, c]))
  const nm = (o) => (lang === 'ar' ? o.name_ar : o.name_en) || o.name_en
  return (
    <div ref={wrap} className="viz" onMouseLeave={tip.hide}>
      <svg ref={svgRef} viewBox={`0 0 ${Math.max(W, left + cw * regions.length)} ${H}`} role="img" aria-label="Gap by theme and region">
        <HatchDefs id="hm-hatch" />
        {regions.map((r, j) => (
          <text key={r.id} x={left + j * cw + cw / 2} y={top - 10} textAnchor="middle" style={{ fontSize: 11, fontWeight: 600 }}>
            {nm(r).length > 14 ? nm(r).slice(0, 13) + '…' : nm(r)}</text>))}
        {rows.map((row, i) => row.header ? (
          <g key={`h-${row.header}`} transform={`translate(0,${ys[i]})`}>
            <text x={4} y={hh - 8} style={{ fontSize: 11, fontWeight: 700, fill: 'var(--ink-2)', letterSpacing: '.04em' }}>{row.header.toUpperCase()}</text>
            <line x1={4} x2={Math.max(W, left + cw * regions.length)} y1={hh - 2} y2={hh - 2} stroke="var(--grid)" />
          </g>
        ) : (() => { const t = row.theme; return (
          <g key={t.id} transform={`translate(0,${ys[i]})`}>
            <text x={left - 10} y={ch / 2 + 4} textAnchor="end" style={{ fontSize: 12, fill: 'var(--ink)' }}>
              <title>{nm(t)}</title>{fitLabel(themeLabel(t, lang), left - 16)}</text>
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
          </g>) })())}
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
