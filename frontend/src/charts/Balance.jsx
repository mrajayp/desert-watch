// Small charts: language balance (diverging Arabic | English bars per theme),
// source mix (stacked bar), a GDELT coverage-history line and monthly collected articles by source.
import * as d3 from 'd3'
import { useRef } from 'react'
import { fmt, sourceLabel } from './scales'
import { fitLabel, groupedRows, themeLabel, useSize, useTooltip } from './util'
import { fmtDate, fmtMonth, pick, t, utcFormat } from '../i18n.js'

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
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={t('Arabic versus English coverage by theme')}>
        <text x={mid - 6} y={12} textAnchor="end" style={{ fontWeight: 600 }}>{t('← Arabic')}</text>
        <text x={mid + 6} y={12} style={{ fontWeight: 600 }}>{t('English →')}</text>
        <line x1={mid} x2={mid} y1={top - 4} y2={H} stroke="var(--axis)" />
        {layout.map((l, i) => {
          if (l.header) return <g key={`h-${l.header}`}><text x={4} y={ys[i] + hh - 10} style={{ fontSize: 11, fontWeight: 700, fill: 'var(--ink-2)', letterSpacing: '.04em' }}>{t(l.header).toUpperCase()}</text></g>
          const r = byId.get(l.theme.id)
          const y = ys[i]
          const total = r.ar + r.en + r.other
          return (
            <g key={r.t.id} onMouseMove={(e) => tip.show(e, <div><b>{pick(r.t, 'name')}</b><div>{r.other
              ? t('{ar} Arabic · {en} English · {other} other', { ar: fmt(r.ar), en: fmt(r.en), other: fmt(r.other) })
              : t('{ar} Arabic · {en} English', { ar: fmt(r.ar), en: fmt(r.en) })}</div>
              <div className="small muted">{t('{pct}% Arabic', { pct: total ? Math.round((r.ar / total) * 100) : 0 })}</div></div>, wrap.current)}>
              <text x={left - 8} y={y + bh - 3} textAnchor="end" style={{ fill: 'var(--ink)', fontSize: 12 }}>
                <title>{lang === 'ar' ? r.t.name_ar : r.t.name_en}</title>{fitLabel(themeLabel(r.t, lang), left - 14)}</text>
              <rect x={mid - x(r.ar) - 1} y={y} width={Math.max(0, x(r.ar))} height={bh} rx={3} fill="var(--scope-libyan)" />
              <rect x={mid + 1} y={y} width={Math.max(0, x(r.en))} height={bh} rx={3} fill="var(--scope-international)" />
              <text x={mid - x(r.ar) - 6} y={y + bh - 4} textAnchor="end" className="num" style={{ fontSize: 11 }}>{fmt(r.ar)}</text>
              <text x={mid + x(r.en) + 6} y={y + bh - 4} className="num" style={{ fontSize: 11 }}>{fmt(r.en)}</text>
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
        {entries.map(([k, v]) => <span key={k}><span className="sw" style={{ background: colors[k] || 'var(--cat-unknown)' }} />{t(labels[k] || k)} {Math.round((v / total) * 100)}%</span>)}
      </div>
    </div>
  )
}

export function HistoryLine({ data, svgRef, markers = [], onPick }) {
  const wrap = useRef(null)
  const W = useSize(wrap, 700)
  const H = 190
  const tip = useTooltip()
  const byDay = new Map((data.all || []).map((d) => [d.day, d.value]))
  if (byDay.size < 2) return <div ref={wrap} className="empty small">{t('No GDELT history collected for this theme yet (GDELT was rate-limiting during collection).')}</div>
  // 7-day mean over calendar days (the days we have among the 7 ending this one). A day GDELT did
  // not give us breaks the line, so a hole is never drawn as a slope.
  const iso = (d) => d.toISOString().slice(0, 10)
  const keys = [...byDay.keys()].sort()
  const roll = d3.utcDay.range(new Date(keys[0]), d3.utcDay.offset(new Date(keys[keys.length - 1]), 1)).map((date) => {
    if (!byDay.has(iso(date))) return { date, v: null }
    const vals = d3.range(7).map((k) => byDay.get(iso(d3.utcDay.offset(date, -k)))).filter((v) => v != null)
    return { date, v: d3.mean(vals), n: vals.length }
  })
  const shown = roll.filter((d) => d.v != null)
  const has = (d) => d.v != null
  const x = d3.scaleUtc().domain(d3.extent(roll, (d) => d.date)).range([36, W - 10])
  const y = d3.scaleLinear().domain([0, d3.max(shown, (d) => d.v)]).nice().range([H - 22, 8])
  const line = d3.line().defined(has).x((d) => x(d.date)).y((d) => y(d.v)).curve(d3.curveMonotoneX)
  const area = d3.area().defined(has).x((d) => x(d.date)).y0(y(0)).y1((d) => y(d.v)).curve(d3.curveMonotoneX)
  const near = (e) => {
    const box = e.currentTarget.getBoundingClientRect()
    return shown[d3.bisector((d) => d.date).center(shown, x.invert(((e.clientX - box.left) / box.width) * W))]
  }
  return (
    <div ref={wrap} className="viz" onMouseLeave={tip.hide}>
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={t('Daily article volume, 7-day average')}
        style={{ cursor: onPick ? 'pointer' : undefined }}
        onClick={(e) => { if (onPick) onPick(iso(near(e).date)) }}
        onMouseMove={(e) => {
          const d = near(e)
          tip.show(e, <div><b>{fmtDate(d.date)}</b><div>{d.n === 7 ? t('{v} articles a day (7-day average)', { v: fmt(d.v) })
            : t('{v} articles a day (average of the {days} days we have in the last 7)', { v: fmt(d.v), days: d.n })}</div>
            {onPick && <div className="small muted">{t('click for our articles that week')}</div>}</div>, wrap.current)
        }}>
        {y.ticks(4).map((v) => <g key={v}><line x1={36} x2={W - 10} y1={y(v)} y2={y(v)} stroke="var(--grid)" /><text x={32} y={y(v) + 3} textAnchor="end">{fmt(v)}</text></g>)}
        {x.ticks(W < 500 ? 4 : 8).map((d) => <text key={+d} x={x(d)} y={H - 6} textAnchor="middle">{utcFormat('%b %y')(d)}</text>)}
        <path d={area(roll)} fill="var(--accent)" fillOpacity={0.1} />
        <path d={line(roll)} fill="none" stroke="var(--accent)" strokeWidth={2} />
        {markers.map((m) => <g key={m.date}><line x1={x(new Date(m.date))} x2={x(new Date(m.date))} y1={8} y2={H - 22} stroke="var(--ink-2)" strokeDasharray="2 3" />
          <text x={x(new Date(m.date)) + 4} y={16}>{m.label}</text></g>)}
      </svg>
      {tip.node}
    </div>
  )
}

// Monthly collected articles stacked by how they reached us, with dated event markers. The month
// still running is hatched.
const MONTH_SOURCES = ['gnews', 'rss', 'backfill', 'galerts', 'other']
const MONTH_COLORS = { gnews: 'var(--al-1)', rss: 'var(--al-2)', backfill: 'var(--al-3)', galerts: 'var(--al-4)', other: 'var(--cat-unknown)' }
const monthSourceLabel = (k) => (k === 'other' ? t('Other') : t(sourceLabel(k)))

export function MonthlyCoverage({ rows, markers = [], svgRef, onPick }) {
  const wrap = useRef(null)
  const W = useSize(wrap, 800)
  const H = 220
  const tip = useTooltip()
  if (!rows || rows.length < 2) return <div ref={wrap} className="empty small">{t('Not enough history for this theme yet.')}</div>
  const data = rows.map((r) => ({ ...r, sources: r.sources || { other: r.total } }))
  const present = MONTH_SOURCES.filter((k) => data.some((d) => d.sources[k] > 0))
  const x = d3.scaleBand().domain(data.map((d) => d.month)).range([36, W - 8]).paddingInner(0.15)
  const y = d3.scaleLinear().domain([0, d3.max(data, (d) => d.total) || 1]).nice().range([H - 24, 14])
  const step = Math.max(1, Math.ceil(data.length / (W < 600 ? 6 : 12)))
  return (
    <div ref={wrap} className="viz" onMouseLeave={tip.hide}>
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={t('Monthly collected articles by source')}>
        <defs>
          <pattern id="mc-partial" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="5" stroke="var(--surface)" strokeWidth="2" />
          </pattern>
        </defs>
        {y.ticks(4).map((v) => <g key={v}><line x1={36} x2={W - 8} y1={y(v)} y2={y(v)} stroke="var(--grid)" /><text x={32} y={y(v) + 3} textAnchor="end">{fmt(v)}</text></g>)}
        {data.map((d, i) => {
          let acc = 0
          return (
            <g key={d.month} style={{ cursor: onPick ? 'pointer' : undefined }} onClick={() => onPick?.(d.month)}
              onMouseMove={(e) => tip.show(e, <div><b>{d.partial ? t('{month} (so far)', { month: fmtMonth(d.month) }) : fmtMonth(d.month)}</b>
                <div>{t('{total} articles: {ar} Arabic, {en} English, {other} in other languages', { total: fmt(d.total), ar: fmt(d.ar), en: fmt(d.en), other: fmt(d.other) })}</div>
                <div>{present.filter((k) => d.sources[k] > 0).map((k) => `${monthSourceLabel(k)} ${fmt(d.sources[k])}`).join(' · ')}</div>
                {d.partial && <div className="small muted">{t('This month is not over yet.')}</div>}
                {onPick && <div className="small muted">{t('click to list them')}</div>}</div>, wrap.current)}>
              <rect x={x(d.month)} y={14} width={x.bandwidth()} height={H - 38} fill="transparent" />
              {present.map((k) => {
                const v = d.sources[k] || 0
                if (!v) return null
                const el = <rect key={k} x={x(d.month)} y={y(acc + v)} width={x.bandwidth()} height={Math.max(0, y(acc) - y(acc + v))} fill={MONTH_COLORS[k]} />
                acc += v
                return el
              })}
              {d.partial && d.total > 0 && <rect x={x(d.month)} y={y(d.total)} width={x.bandwidth()} height={Math.max(0, y(0) - y(d.total))} fill="url(#mc-partial)" />}
              {i % step === 0 && <text x={x(d.month) + x.bandwidth() / 2} y={H - 8} textAnchor="middle">{utcFormat('%b %y')(new Date(`${d.month}-01T00:00:00Z`))}</text>}
            </g>)
        })}
        {markers.map((m) => {
          const k = m.date.slice(0, 7) // i18n-ok: the month band of the marker, not shown
          if (x(k) == null) return null
          const mx = x(k) + x.bandwidth() / 2
          return <g key={m.date + m.label}><line x1={mx} x2={mx} y1={10} y2={H - 24} stroke="var(--ink)" strokeOpacity={0.5} />
            <circle cx={mx} cy={10} r={4} fill="var(--surface)" stroke="var(--ink)" strokeWidth={1.5}
              onMouseMove={(e) => tip.show(e, <div><b>{fmtDate(m.date)}</b><div>{pick(m, 'label')}</div></div>, wrap.current)} /></g>
        })}
      </svg>
      {tip.node}
      <div className="legend">
        {present.map((k) => <span key={k}><span className="sw" style={{ background: MONTH_COLORS[k] }} />{monthSourceLabel(k)}</span>)}
        {data.some((d) => d.partial) && <span><svg width="14" height="12" style={{ verticalAlign: -2, marginInlineEnd: 5 }}>
          <rect width="14" height="12" rx="2" fill="var(--al-1)" /><rect width="14" height="12" rx="2" fill="url(#mc-partial)" /></svg>{t('This month so far')}</span>}
        <span><svg width="10" height="10"><circle cx="5" cy="5" r="3.5" fill="none" stroke="var(--ink)" strokeWidth="1.5" /></svg> {t('dated event (hover)')}</span>
        <span className="muted">{t('Older months come from searching Google News back by date, which finds fewer articles. Compare the ups and downs within a year. The totals across years don’t compare.')}</span>
      </div>
    </div>
  )
}
