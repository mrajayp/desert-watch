// Daily numbers from outside the news (exchange rates, Wikipedia pages people in Libya looked up).
// Indicators that share a chart key (same unit) are drawn together, for example the parallel and
// official dollar. Each chart has its own labelled axis. A day with no value breaks the line.
// Payload: /api/indicators. Never put on one axis with article counts.
import * as d3 from 'd3'
import { useRef } from 'react'
import { fmt } from './scales'
import { useSize, useTooltip } from './util'
import { fmtDate, fmtNum, pick, t, utcFormat } from '../i18n.js'

const iso = (d) => d.toISOString().slice(0, 10)
// a money figure with two decimals, in the interface language's decimal mark
const money2 = (v, d = 2) => fmtNum(v, { minimumFractionDigits: d, maximumFractionDigits: d, useGrouping: false })
const STYLE = {
  main: { stroke: 'var(--accent)', dash: null, width: 1.8 },
  alt: { stroke: 'var(--accent)', dash: '4 3', width: 1.2 },
  ref: { stroke: 'var(--ink-2)', dash: null, width: 1.4 },
}
const styleOf = (ind) => STYLE[ind.style] || STYLE.main

// indicators -> charts: one per chart key (or per indicator when it has none), in payload order
export function chartGroups(indicators, titles = {}) {
  const out = []
  for (const ind of indicators) {
    const key = ind.chart || ind.key
    let g = out.find((x) => x.key === key)
    if (!g) out.push((g = { key, title: titles[ind.chart] || pick(ind, 'label'), unit: ind.unit, lines: [] }))
    g.lines.push(ind)
  }
  return out
}

function Chart({ group, width, onPickDay }) {
  const wrap = useRef(null)
  const tip = useTooltip()
  const H = 140, L = 40, R = 8, T = 12, B = 20
  const series = group.lines.map((ind) => ({ ind, rows: ind.rows.map((r) => ({ date: new Date(r.day + 'T00:00:00Z'), v: r.value })) }))
  const all = series.flatMap((x) => x.rows)
  const shown = all.filter((r) => r.v != null)
  if (shown.length < 2) return <div className="empty small">{t('Not enough days yet.')}</div>
  const x = d3.scaleUtc().domain(d3.extent(all, (r) => r.date)).range([L, width - R])
  // the unit arrives in the interface language; the exchange-rate source says the same in any language
  const money = group.unit === 'dinars' || group.lines.every((ind) => ind.source === 'exchange')
  const [lo, hi] = d3.extent(shown, (r) => r.v)
  const y = d3.scaleLinear().domain([money ? lo * 0.95 : 0, hi]).nice().range([H - B, T])
  const line = d3.line().defined((r) => r.v != null).x((r) => x(r.date)).y((r) => y(r.v))
  const days = [...new Set(all.map((r) => iso(r.date)))].sort()
  const near = (e) => {
    const box = e.currentTarget.getBoundingClientRect()
    const t = x.invert(((e.clientX - box.left) / box.width) * width)
    return days[d3.bisector((d) => new Date(d + 'T00:00:00Z')).center(days, t)]
  }
  const valueOn = (s, day) => s.rows.find((r) => iso(r.date) === day)?.v
  const say = (s, day) => {
    const v = valueOn(s, day)
    if (v != null) return `${money ? money2(v) : fmt(v)} ${s.ind.unit}`
    return s.ind.source === 'wikimedia_dp' ? t('fewer than about 90 views') : t('no figure that day')
  }
  return (
    <div ref={wrap} className="viz" onMouseLeave={tip.hide}>
      <svg viewBox={`0 0 ${width} ${H}`} role="img" aria-label={t('{title}, daily', { title: group.title })} style={{ cursor: onPickDay ? 'pointer' : undefined }}
        onMouseMove={(e) => {
          const day = near(e)
          tip.show(e, <div><b>{fmtDate(day)}</b>{series.map((s) => <div key={s.ind.key}>{group.lines.length > 1 ? `${pick(s.ind, 'label')}: ` : ''}{say(s, day)}</div>)}
            {onPickDay && <div className="small muted">{t('click for the economy articles that week')}</div>}</div>, wrap.current)
        }}
        onClick={(e) => onPickDay?.(near(e))}>
        {y.ticks(3).map((v) => <g key={v}><line x1={L} x2={width - R} y1={y(v)} y2={y(v)} stroke="var(--grid)" />
          <text x={L - 4} y={y(v) + 3} textAnchor="end" style={{ fontSize: 11 }}>{money ? money2(v, 1) : fmt(v)}</text></g>)}
        {x.ticks(width < 420 ? 3 : 6).map((d) => <text key={+d} x={x(d)} y={H - 5} textAnchor="middle" style={{ fontSize: 11 }}>{utcFormat('%b %y')(d)}</text>)}
        <text x={L} y={T - 2} style={{ fontSize: 11, fill: 'var(--muted)' }}>{group.unit}</text>
        {series.map((s) => {
          const st = styleOf(s.ind)
          const last = s.rows.filter((r) => r.v != null).at(-1)
          return <g key={s.ind.key}>
            <path d={line(s.rows)} fill="none" stroke={st.stroke} strokeWidth={st.width} strokeDasharray={st.dash || undefined} />
            {last && <circle cx={x(last.date)} cy={y(last.v)} r={2.5} fill={st.stroke} />}
          </g>
        })}
      </svg>
      {group.lines.length > 1 && (
        <div className="legend" style={{ marginTop: 2 }}>
          {group.lines.map((ind) => {
            const st = styleOf(ind)
            return <span key={ind.key}><svg width="18" height="8" style={{ verticalAlign: 1, marginInlineEnd: 4 }}>
              <line x1="0" x2="18" y1="4" y2="4" stroke={st.stroke} strokeWidth={st.width + 0.4} strokeDasharray={st.dash || undefined} /></svg>{pick(ind, 'label')}</span>
          })}
        </div>)}
      {tip.node}
    </div>
  )
}

export default function IndicatorLines({ indicators, charts, onPickDay }) {
  const wrap = useRef(null)
  const W = useSize(wrap, 900)
  const cols = W < 640 ? 1 : 2
  const width = Math.max(240, Math.floor((W - 16 * (cols - 1)) / cols) - 4)
  if (!indicators?.length) return <div ref={wrap} className="empty small">{t('No signals collected yet.')}</div>
  const groups = chartGroups(indicators, charts)
  const notes = [...new Set(indicators.map((i) => i.note).filter(Boolean))]   // one note per source, not per chart
  return (
    <div ref={wrap} style={{ display: 'grid', gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`, gap: 16 }}>
      {groups.map((g) => (
        <div key={g.key}>
          <div className="small" style={{ fontWeight: 600, marginBottom: 2 }}>{g.title}</div>
          <Chart group={g} width={width} onPickDay={onPickDay} />
        </div>))}
      {notes.length > 0 && <div className="small muted" style={{ gridColumn: '1 / -1' }}>{notes.join(' ')}</div>}
    </div>
  )
}
