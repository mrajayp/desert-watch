// Small charts: language balance (diverging Arabic | English bars per theme),
// source mix (stacked bar), and a GDELT coverage-history line.
import * as d3 from 'd3'
import { useRef } from 'react'
import { fmt } from './scales'
import { fitLabel, groupedRows, themeLabel, useSize, useTooltip } from './util'

export function LanguageBalance({ themes, cells, lang = 'en', svgRef }) {
  const wrap = useRef(null)
  const W = useSize(wrap, 500)
  const tip = useTooltip()
  const rows = themes.map((t) => {
    const c = cells.find((x) => x.theme_id === t.id)
    const l = c?.breakdown?.lang || {}
    return { t, ar: l.ar || 0, en: l.en || 0, other: Object.entries(l).filter(([k]) => k !== 'ar' && k !== 'en').reduce((a, [, v]) => a + v, 0) }
  })
  const left = Math.min(230, Math.max(110, W * 0.36))
  const mid = left + (W - left) / 2
  const max = d3.max(rows, (r) => Math.max(r.ar, r.en)) || 1
  const numRoom = 38 // space for the count at each bar end
  const x = d3.scaleLinear().domain([0, max]).range([0, Math.max(10, (W - left) / 2 - numRoom - 6)])
  const bh = 16, gap = 14, top = 22, hh = 24
  const layout = groupedRows(rows.map((r) => r.t))
  const byId = new Map(rows.map((r) => [r.t.id, r]))
  const ys = []
  let yy = top
  layout.forEach((l) => { ys.push(yy); yy += l.header ? hh : bh + gap })
  const H = yy
  return (
    <div ref={wrap} className="viz" onMouseLeave={tip.hide}>
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Arabic versus English coverage by theme">
        <text x={mid - 6} y={12} textAnchor="end" style={{ fontWeight: 600 }}>← Arabic</text>
        <text x={mid + 6} y={12} style={{ fontWeight: 600 }}>English →</text>
        <line x1={mid} x2={mid} y1={top - 4} y2={H} stroke="var(--axis)" />
        {layout.map((l, i) => {
          if (l.header) return <g key={`h-${l.header}`}><text x={4} y={ys[i] + hh - 10} style={{ fontSize: 11, fontWeight: 700, fill: 'var(--ink-2)', letterSpacing: '.04em' }}>{l.header.toUpperCase()}</text></g>
          const r = byId.get(l.theme.id)
          const y = ys[i]
          const total = r.ar + r.en + r.other
          return (
            <g key={r.t.id} onMouseMove={(e) => tip.show(e, <div><b>{r.t.name_en}</b><div>{fmt(r.ar)} Arabic · {fmt(r.en)} English{r.other ? ` · ${fmt(r.other)} other` : ''}</div>
              <div className="small muted">{total ? Math.round((r.ar / total) * 100) : 0}% Arabic</div></div>, wrap.current)}>
              <text x={left - 8} y={y + bh - 3} textAnchor="end" style={{ fill: 'var(--ink)', fontSize: 12 }}>
                <title>{lang === 'ar' ? r.t.name_ar : r.t.name_en}</title>{fitLabel(themeLabel(r.t, lang), left - 14)}</text>
              <rect x={mid - x(r.ar) - 1} y={y} width={Math.max(0, x(r.ar))} height={bh} rx={3} fill="var(--scope-libyan)" />
              <rect x={mid + 1} y={y} width={Math.max(0, x(r.en))} height={bh} rx={3} fill="var(--scope-international)" />
              <text x={mid - x(r.ar) - 6} y={y + bh - 4} textAnchor="end" className="num" style={{ fontSize: 10.5 }}>{fmt(r.ar)}</text>
              <text x={mid + x(r.en) + 6} y={y + bh - 4} className="num" style={{ fontSize: 10.5 }}>{fmt(r.en)}</text>
            </g>)
        })}
      </svg>
      {tip.node}
    </div>
  )
}

export function MixBar({ parts, colors, labels, height = 12 }) {
  const total = d3.sum(Object.values(parts)) || 1
  let acc = 0
  const entries = Object.entries(parts).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1])
  return (
    <div>
      <svg viewBox={`0 0 100 ${height}`} preserveAspectRatio="none" style={{ width: '100%', height }}>
        {entries.map(([k, v]) => {
          const w = (v / total) * 100
          const el = <rect key={k} x={acc} y={0} width={Math.max(0, w - 0.4)} height={height} fill={colors[k] || 'var(--cat-unknown)'} />
          acc += w
          return el
        })}
      </svg>
      <div className="legend" style={{ marginTop: 4 }}>
        {entries.map(([k, v]) => <span key={k}><span className="sw" style={{ background: colors[k] || 'var(--cat-unknown)' }} />{labels[k] || k} {Math.round((v / total) * 100)}%</span>)}
      </div>
    </div>
  )
}

export function HistoryLine({ data, svgRef, markers = [], onPick }) {
  const wrap = useRef(null)
  const W = useSize(wrap, 700)
  const H = 190
  const tip = useTooltip()
  const all = (data.all || []).map((d) => ({ ...d, date: new Date(d.day) }))
  if (all.length < 2) return <div ref={wrap} className="empty small">No GDELT history collected for this theme yet (GDELT was rate-limiting during collection).</div>
  // 7-day rolling mean to tame daily noise
  const roll = all.map((d, i) => ({ date: d.date, v: d3.mean(all.slice(Math.max(0, i - 6), i + 1), (x) => x.value) }))
  const x = d3.scaleUtc().domain(d3.extent(roll, (d) => d.date)).range([36, W - 10])
  const y = d3.scaleLinear().domain([0, d3.max(roll, (d) => d.v)]).nice().range([H - 22, 8])
  const line = d3.line().x((d) => x(d.date)).y((d) => y(d.v)).curve(d3.curveMonotoneX)
  const area = d3.area().x((d) => x(d.date)).y0(y(0)).y1((d) => y(d.v)).curve(d3.curveMonotoneX)
  return (
    <div ref={wrap} className="viz" onMouseLeave={tip.hide}>
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Daily article volume, 7-day average"
        style={{ cursor: onPick ? 'pointer' : undefined }}
        onClick={(e) => {
          if (!onPick) return
          const box = e.currentTarget.getBoundingClientRect()
          const dt = x.invert(((e.clientX - box.left) / box.width) * W)
          onPick(roll[d3.bisector((d) => d.date).center(roll, dt)].date.toISOString().slice(0, 10))
        }}
        onMouseMove={(e) => {
          const box = e.currentTarget.getBoundingClientRect()
          const dt = x.invert(((e.clientX - box.left) / box.width) * W)
          const i = d3.bisector((d) => d.date).center(roll, dt)
          tip.show(e, <div><b>{roll[i].date.toISOString().slice(0, 10)}</b><div>{fmt(roll[i].v)} articles/day (7-day avg)</div>{onPick && <div className="small muted">click for our articles that week</div>}</div>, wrap.current)
        }}>
        {y.ticks(4).map((v) => <g key={v}><line x1={36} x2={W - 10} y1={y(v)} y2={y(v)} stroke="var(--grid)" /><text x={32} y={y(v) + 3} textAnchor="end">{fmt(v)}</text></g>)}
        {x.ticks(W < 500 ? 4 : 8).map((t) => <text key={+t} x={x(t)} y={H - 6} textAnchor="middle">{d3.utcFormat('%b %y')(t)}</text>)}
        <path d={area(roll)} fill="var(--accent)" fillOpacity={0.1} />
        <path d={line(roll)} fill="none" stroke="var(--accent)" strokeWidth={2} />
        {markers.map((m) => <g key={m.date}><line x1={x(new Date(m.date))} x2={x(new Date(m.date))} y1={8} y2={H - 22} stroke="var(--ink-2)" strokeDasharray="2 3" />
          <text x={x(new Date(m.date)) + 4} y={16}>{m.label}</text></g>)}
      </svg>
      {tip.node}
    </div>
  )
}

// Monthly collected articles (stacked Arabic | English), with dated event markers.
export function MonthlyCoverage({ rows, markers = [], svgRef, onPick }) {
  const wrap = useRef(null)
  const W = useSize(wrap, 800)
  const H = 220
  const tip = useTooltip()
  if (!rows || rows.length < 2) return <div ref={wrap} className="empty small">Not enough history for this theme yet.</div>
  const data = rows.map((r) => ({ ...r, date: new Date(r.month + '-01T00:00:00Z') }))
  const x = d3.scaleBand().domain(data.map((d) => d.month)).range([36, W - 8]).paddingInner(0.15)
  const y = d3.scaleLinear().domain([0, d3.max(data, (d) => d.total) || 1]).nice().range([H - 24, 14])
  const step = Math.max(1, Math.ceil(data.length / (W < 600 ? 6 : 12)))
  return (
    <div ref={wrap} className="viz" onMouseLeave={tip.hide}>
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Monthly collected articles, Arabic and English">
        {y.ticks(4).map((v) => <g key={v}><line x1={36} x2={W - 8} y1={y(v)} y2={y(v)} stroke="var(--grid)" /><text x={32} y={y(v) + 3} textAnchor="end">{fmt(v)}</text></g>)}
        {data.map((d, i) => (
          <g key={d.month} style={{ cursor: onPick ? 'pointer' : undefined }} onClick={() => onPick?.(d.month)}
            onMouseMove={(e) => tip.show(e, <div><b>{d.month}</b><div>{fmt(d.total)} articles · {fmt(d.ar)} Arabic · {fmt(d.en)} English</div>{onPick && <div className="small muted">click to list them</div>}</div>, wrap.current)}>
            <rect x={x(d.month)} y={14} width={x.bandwidth()} height={H - 38} fill="transparent" />
            <rect x={x(d.month)} y={y(d.ar)} width={x.bandwidth()} height={Math.max(0, y(0) - y(d.ar))} fill="var(--scope-libyan)" />
            <rect x={x(d.month)} y={y(d.ar + d.en + d.other)} width={x.bandwidth()} height={Math.max(0, y(d.ar) - y(d.ar + d.en + d.other) - (d.en + d.other ? 1 : 0))} rx={2} fill="var(--scope-international)" />
            {i % step === 0 && <text x={x(d.month) + x.bandwidth() / 2} y={H - 8} textAnchor="middle">{d.month}</text>}
          </g>))}
        {markers.map((m) => {
          const k = m.date.slice(0, 7)
          if (x(k) == null) return null
          const mx = x(k) + x.bandwidth() / 2
          return <g key={m.date + m.label}><line x1={mx} x2={mx} y1={10} y2={H - 24} stroke="var(--ink)" strokeOpacity={0.5} />
            <circle cx={mx} cy={10} r={4} fill="var(--surface)" stroke="var(--ink)" strokeWidth={1.5}
              onMouseMove={(e) => tip.show(e, <div><b>{m.date}</b><div>{m.label}</div></div>, wrap.current)} /></g>
        })}
      </svg>
      {tip.node}
      <div className="legend">
        <span><span className="sw" style={{ background: 'var(--scope-libyan)' }} />Arabic</span>
        <span><span className="sw" style={{ background: 'var(--scope-international)' }} />English</span>
        <span><svg width="10" height="10"><circle cx="5" cy="5" r="3.5" fill="none" stroke="var(--ink)" strokeWidth="1.5" /></svg> dated event (hover)</span>
        <span className="muted">Older months come from backfilled search, which returns fewer items: compare shapes, not levels, across years.</span>
      </div>
    </div>
  )
}
