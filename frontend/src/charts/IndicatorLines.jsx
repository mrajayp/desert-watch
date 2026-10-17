// Daily numbers from outside the news (Wikipedia pages people in Libya looked up, exchange rates),
// one small line each on its own labelled axis. A day with no value breaks the line. Payload:
// /api/indicators. Never compared with coverage on one axis: each line keeps its own unit.
import * as d3 from 'd3'
import { useRef } from 'react'
import { fmt } from './scales'
import { useSize, useTooltip } from './util'

const iso = (d) => d.toISOString().slice(0, 10)

function Line({ ind, width, onPickDay }) {
  const wrap = useRef(null)
  const tip = useTooltip()
  const H = 130, L = 40, R = 8, T = 10, B = 20
  const rows = ind.rows.map((r) => ({ date: new Date(r.day + 'T00:00:00Z'), v: r.value }))
  const shown = rows.filter((r) => r.v != null)
  if (shown.length < 2) return <div className="empty small">Not enough days yet.</div>
  const x = d3.scaleUtc().domain(d3.extent(rows, (r) => r.date)).range([L, width - R])
  const lo = ind.unit === 'dinars' ? d3.min(shown, (r) => r.v) * 0.95 : 0
  const y = d3.scaleLinear().domain([lo, d3.max(shown, (r) => r.v)]).nice().range([H - B, T])
  const line = d3.line().defined((r) => r.v != null).x((r) => x(r.date)).y((r) => y(r.v))
  const last = shown[shown.length - 1]
  const near = (e) => {
    const box = e.currentTarget.getBoundingClientRect()
    return rows[d3.bisector((r) => r.date).center(rows, x.invert(((e.clientX - box.left) / box.width) * width))]
  }
  const say = (r) => (r.v != null ? `${fmt(r.v)} ${ind.unit}` : ind.source === 'wikimedia_dp' ? 'fewer than about 90 views (below the threshold)' : 'no reading')
  return (
    <div ref={wrap} className="viz" onMouseLeave={tip.hide}>
      <svg viewBox={`0 0 ${width} ${H}`} role="img" aria-label={`${ind.label}, daily`} style={{ cursor: onPickDay ? 'pointer' : undefined }}
        onMouseMove={(e) => { const r = near(e); tip.show(e, <div><b>{iso(r.date)}</b><div>{say(r)}</div>{onPickDay && <div className="small muted">click for the economy articles that week</div>}</div>, wrap.current) }}
        onClick={(e) => onPickDay?.(iso(near(e).date))}>
        {y.ticks(3).map((v) => <g key={v}><line x1={L} x2={width - R} y1={y(v)} y2={y(v)} stroke="var(--grid)" />
          <text x={L - 4} y={y(v) + 3} textAnchor="end" style={{ fontSize: 9 }}>{fmt(v)}</text></g>)}
        {x.ticks(width < 420 ? 3 : 6).map((t) => <text key={+t} x={x(t)} y={H - 5} textAnchor="middle" style={{ fontSize: 9 }}>{d3.utcFormat('%b %y')(t)}</text>)}
        <text x={L} y={T - 1} style={{ fontSize: 9, fill: 'var(--muted)' }}>{ind.unit}</text>
        <path d={line(rows)} fill="none" stroke="var(--accent)" strokeWidth={1.6} />
        <circle cx={x(last.date)} cy={y(last.v)} r={3} fill="var(--accent)" />
      </svg>
      {tip.node}
    </div>
  )
}

export default function IndicatorLines({ indicators, onPickDay }) {
  const wrap = useRef(null)
  const W = useSize(wrap, 900)
  const cols = W < 640 ? 1 : 2
  const width = Math.max(240, Math.floor((W - 16 * (cols - 1)) / cols) - 4)
  if (!indicators?.length) return <div ref={wrap} className="empty small">No signals collected yet.</div>
  const notes = [...new Set(indicators.map((i) => i.note).filter(Boolean))]   // one note per source, not per chart
  return (
    <div ref={wrap} style={{ display: 'grid', gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`, gap: 16 }}>
      {indicators.map((ind) => (
        <div key={ind.key}>
          <div className="small" style={{ fontWeight: 600, marginBottom: 2 }}>{ind.label}</div>
          <Line ind={ind} width={width} onPickDay={onPickDay} />
        </div>))}
      {notes.length > 0 && <div className="small muted" style={{ gridColumn: '1 / -1' }}>{notes.join(' ')}</div>}
    </div>
  )
}
