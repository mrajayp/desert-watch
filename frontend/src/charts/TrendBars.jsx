// Articles per week, one small panel per theme (Trends page). Bars = articles that week from the
// comparable outlets (the set the gap score counts), grey step = the usual level for that much need
// (expected_week), strip = the verdict for the 4 weeks ending that week. Every number in the
// tooltip is one that is drawn. Payload: /api/cells/trends.
import * as d3 from 'd3'
import { memo, useRef, useState } from 'react'
import { fmt, gapFill } from './scales'
import { HatchDefs, themeLabel, useSize, useTooltip } from './util'

// per lens: the need in the tooltip, the usual-level phrase, and the words when a theme has none
export const LENS_NEED = {
  audience: { label: 'Wikipedia views', usual: 'this much reader interest', none: 'No reader data linked to this theme', short: 'No reader data' },
  events: { label: 'Conflict and protest events', usual: 'this many events', none: 'No event data linked to this theme', short: 'No event data' },
  humanitarian: { label: 'ReliefWeb reports', usual: 'this many ReliefWeb reports', none: 'No ReliefWeb reports linked to this theme', short: 'No ReliefWeb data' },
  journalist: { label: 'Gaps flagged by the team', usual: 'this many team flags', none: 'No team flags on this theme', short: 'No team flags' },
}
export const lensNeed = (lens) => LENS_NEED[lens] || LENS_NEED.audience

// why a week is not judged: [pill, sentence]
const REASONS = {
  too_few_expected: ['Too few articles to judge', 'Too few articles expected to judge'],
  building_baseline: ['Still building a baseline', 'We are still building a baseline for this theme'],
  in_progress: ['Still coming in', 'This week is still coming in'],
}
const reasonText = (reason, need, long) => (reason === 'no_need_data' ? (long ? need.none : need.short)
  : (REASONS[reason] || ['Not scored yet', 'Not scored yet'])[long ? 1 : 0])

const times = (g) => { const x = Math.exp(g); return x >= 10 ? String(Math.round(x)) : x.toFixed(1) }
export const shortfall = (g, red) => (g >= red ? `About ${times(g)} times fewer articles than usual` : 'About as usual')
const articles = (n) => `${fmt(n)} article${n === 1 ? '' : 's'}`
const about = (v) => (v >= 1 ? `about ${fmt(v)}` : 'less than 1')
const judged = (r) => !r.in_progress && !r.insufficient && r.gap != null

export function verdict(r, red, need) {
  if (r.in_progress) return 'This week is still coming in. Not judged yet.'
  if (!judged(r)) return `Last 4 weeks: not judged. ${reasonText(r.reason, need, true)}.`
  return `Last 4 weeks: ${articles(r.articles_4w)} against ${about(r.expected_4w)} usual. ${shortfall(r.gap, red)}.`
}

const DAY = 864e5
const utc = (s) => new Date(s + 'T00:00:00Z')
export const weekEnd = (w) => new Date(utc(w).getTime() + 6 * DAY).toISOString().slice(0, 10)
export function weekRange(w) {
  const a = utc(w), b = new Date(a.getTime() + 6 * DAY), f = d3.utcFormat
  if (a.getUTCFullYear() !== b.getUTCFullYear()) return `${f('%-d %b %Y')(a)} to ${f('%-d %b %Y')(b)}`
  if (a.getUTCMonth() !== b.getUTCMonth()) return `${f('%-d %b')(a)} to ${f('%-d %b %Y')(b)}`
  return `${f('%-d')(a)} to ${f('%-d %b %Y')(b)}`
}

// linear from 0 with 3-4 labelled gridlines (0 included) ending on the top of the domain
function yScale(top, range) {
  for (const n of [3, 2, 4]) {
    const hi = d3.nice(0, top, n)[1]
    const ticks = d3.ticks(0, hi, n)
    if (ticks.length >= 3 && ticks.length <= 4 && ticks[ticks.length - 1] === hi) return [d3.scaleLinear().domain([0, hi]).range(range), ticks]
  }
  const y = d3.scaleLinear().domain([0, top]).nice(3).range(range)
  return [y, y.ticks(3)]
}

function needLine(r, need, lens) {
  if (r.need_week == null) return null
  const so = r.in_progress ? ' so far' : ''
  const split = r.need_en != null ? ` (English ${fmt(r.need_en)}, Arabic ${fmt(r.need_ar)})` : ''
  const trimmed = r.need_week_raw > r.need_week + 0.5 ? ` Before we trimmed one-day spikes: ${fmt(r.need_week_raw)}.` : ''
  return `${need.label}${so}: ${fmt(r.need_week)}${lens === 'audience' ? split : ''}.${trimmed}`
}

const Panel = memo(function Panel({ t, rows, hasNeed, width, lens, red, lang, selected, onSelect, onPickWeek, onPickBar }) {
  const wrap = useRef(null)
  const tip = useTooltip()
  const [hover, setHover] = useState(null)
  const need = lensNeed(lens)
  const name = (lang === 'ar' ? t.name_ar : t.name_en) || t.name_en
  const L = 30, R = 4, T = 16, y0 = 116, sy = y0 + 3, sh = 7, H = sy + sh + 15
  const xs = d3.scaleBand().domain(rows.map((r) => r.week)).range([L, width - R])
  const step = xs.step()
  // no usual level on the week still coming in: its need is not complete either
  const lined = (r) => hasNeed && !r.in_progress && r.expected_week != null
  const [y, ticks] = yScale(Math.max(4, d3.max(rows, (r) => r.articles) || 0,
    d3.max(rows, (r) => (lined(r) ? r.expected_week : 0)) || 0), [y0, T])
  // usual level as a step line: one flat segment per week, broken where there is none
  let path = '', open = false
  for (const r of rows) {
    if (!lined(r)) { open = false; continue }
    const x0 = xs(r.week), yy = y(r.expected_week).toFixed(1)
    path += `${open ? `V${yy}` : `M${x0.toFixed(1)},${yy}`}H${(x0 + step).toFixed(1)}`
    open = true
  }
  const done = rows.filter((r) => !r.in_progress)
  const last = done[done.length - 1]
  const cur = rows.find((r) => r.in_progress)
  const a4 = last ? last.articles_4w ?? d3.sum(done.slice(-4), (r) => r.articles) : 0
  // month labels at the 1st of each month (quarters only on narrow panels), January shows the year
  const first = utc(rows[0].week)
  const months = d3.utcMonth.range(d3.utcMonth.ceil(first), new Date(utc(rows[rows.length - 1].week).getTime() + 7 * DAY))
    .filter((m) => width >= 420 || m.getUTCMonth() % 3 === 0)
    .map((m) => ({ m, x: L + ((m - first) / (7 * DAY)) * step }))
    .filter((d) => d.x < width - R - 16)
  const at = (e) => {
    const box = e.currentTarget.ownerSVGElement.getBoundingClientRect()
    const px = ((e.clientX - box.left) / box.width) * width
    return Math.max(0, Math.min(rows.length - 1, Math.floor((px - L) / step)))
  }
  const show = (e) => {
    const i = at(e), r = rows[i]
    setHover(i)
    const nl = hasNeed ? needLine(r, need, lens) : null
    tip.show(e, (
      <div>
        <b>{weekRange(r.week)}</b>
        <div>{articles(r.articles)} from outlets we followed all year{r.in_progress ? ' so far' : ''}</div>
        {r.articles_all !== r.articles && <div>{articles(r.articles_all)} from all sources</div>}
        {lined(r) && <div>Usual for this week: {about(r.expected_week)}</div>}
        {nl && <div>{nl}</div>}
        <div style={{ marginTop: 4 }}>{verdict(r, red, need)}</div>
        {onPickBar && <div className="small muted">Click for this week’s articles</div>}
      </div>), wrap.current)
  }
  const hide = () => { setHover(null); tip.hide() }
  const curX = cur ? xs(cur.week) + step / 2 : null
  return (
    <div ref={wrap} className="card viz trend-panel">
      <div className="trend-head">
        <button type="button" className="linkish" aria-pressed={!!selected} title={`${name}. Show this theme in the charts below.`}
          onClick={() => onSelect?.(t.id)}>{themeLabel(t, lang)}</button>
        {last && (
          <button type="button" className={judged(last) && last.gap >= red ? 'pill flag' : 'pill'}
            title={`${weekRange(last.week)}. ${verdict(last, red, need)} Click for the full gap.`}
            onClick={() => onPickWeek?.(t.id, last.week)}>
            {judged(last) ? shortfall(last.gap, red) : reasonText(last.reason, need, false)}</button>)}
      </div>
      <div className="small muted" style={{ margin: '2px 0 4px' }}>
        Last 4 weeks: {articles(a4)}.{hasNeed && last?.expected_4w != null ? ` Usual: ${about(last.expected_4w)}.` : ''}</div>
      <svg viewBox={`0 0 ${width} ${H}`} role="img" aria-label={`${name}: articles per week`}>
        <HatchDefs id={`tb-hatch-${t.id}`} />
        {hover != null && <rect x={xs(rows[hover].week)} y={T} width={step} height={y0 - T} fill="var(--surface-2)" />}
        {ticks.map((v) => (
          <g key={v}><line x1={L} x2={width - R} y1={y(v)} y2={y(v)} stroke="var(--grid)" />
            <text x={L - 4} y={y(v) + 3} textAnchor="end" className="num" style={{ fontSize: 9 }}>{fmt(v)}</text></g>))}
        <text x={L} y={9} style={{ fontSize: 9, fill: 'var(--muted)' }}>articles a week</text>
        {rows.map((r) => {
          const x = xs(r.week) + step * 0.12, w = Math.max(1, step * 0.76), top = y(r.articles)
          if (r.in_progress) {
            return <rect key={r.week} x={x + 0.5} y={top + 0.5} width={Math.max(0.5, w - 1)} height={Math.max(0, y0 - top - 0.5)}
              fill="none" stroke="var(--accent)" strokeWidth={1} strokeDasharray="2 1.5" />
          }
          return r.articles > 0 ? <rect key={r.week} x={x} y={top} width={w} height={y0 - top} fill="var(--accent)" /> : null
        })}
        {hasNeed ? (path && <path d={path} fill="none" stroke="var(--ink-2)" strokeWidth={1.6} strokeLinejoin="round" />)
          : <text x={L + 4} y={T + 9} className="halo" style={{ fontSize: 10, fill: 'var(--muted)' }}>{need.none}</text>}
        {cur && <g>
          <line x1={curX} x2={curX} y1={11} y2={Math.max(11, y(cur.articles) - 2)} stroke="var(--muted)" strokeDasharray="1 2" />
          <text x={width - R} y={9} textAnchor="end" style={{ fontSize: 9, fill: 'var(--muted)' }}>still coming in</text></g>}
        <rect x={L} y={T} width={width - R - L} height={y0 - T} fill="transparent" style={{ cursor: onPickBar ? 'pointer' : 'default' }}
          onMouseMove={show} onMouseLeave={hide} onClick={(e) => onPickBar?.(t, rows[at(e)])} />
        {rows.map((r) => {
          const fill = r.in_progress ? null : judged(r) ? (r.gap >= red ? gapFill(r) : 'var(--gap-0)') : `url(#tb-hatch-${t.id})`
          return (
            <rect key={r.week} x={xs(r.week)} y={sy} width={step + 0.3} height={sh} fill={fill || 'transparent'}
              style={{ cursor: fill && onPickWeek ? 'pointer' : 'default' }} onClick={fill ? () => onPickWeek?.(t.id, r.week) : undefined}>
              <title>{`${weekRange(r.week)}. ${verdict(r, red, need)}${fill ? ' Click for the full gap.' : ''}`}</title></rect>)
        })}
        {months.map(({ m, x }) => (
          <g key={+m}><line x1={x} x2={x} y1={sy + sh} y2={sy + sh + 3} stroke="var(--axis)" />
            <text x={x + 2} y={sy + sh + 12} style={{ fontSize: 9 }}>{m.getUTCMonth() === 0 ? m.getUTCFullYear() : d3.utcFormat('%b')(m)}</text></g>))}
      </svg>
      {tip.node}
    </div>
  )
})

// themes grouped like the heatmap: General first, then each group with its own heading
function themeGroups(themes) {
  const plain = themes.filter((t) => !t.group)
  const named = [...new Set(themes.filter((t) => t.group).map((t) => t.group))]
  return [
    ...(plain.length ? [{ label: 'General', themes: plain }] : []),
    ...named.map((g) => ({ label: g[0].toUpperCase() + g.slice(1), themes: themes.filter((t) => t.group === g) })),
  ]
}

export default function TrendBars({ themes, data, lens, lang = 'en', selectedId, onSelect, onPickWeek, onPickBar }) {
  const wrap = useRef(null)
  const W = useSize(wrap, 900)
  const cols = W < 560 ? 1 : W < 900 ? 2 : 3
  const width = Math.max(220, Math.floor((W - 12 * (cols - 1)) / cols) - 22) // card padding + border
  const red = data.red_from ?? 0.4
  const need = lensNeed(lens)
  const groups = themeGroups(themes.filter((t) => data.themes?.[t.id]?.rows?.length))
  return (
    <div ref={wrap}>
      {groups.map((g) => (
        <div key={g.label}>
          {groups.length > 1 && <div className="trend-group">{g.label}</div>}
          <div className="trend-grid" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}>
            {g.themes.map((t) => (
              <Panel key={t.id} t={t} rows={data.themes[t.id].rows} hasNeed={data.themes[t.id].has_need} width={width}
                lens={lens} red={red} lang={lang} selected={t.id === selectedId}
                onSelect={onSelect} onPickWeek={onPickWeek} onPickBar={onPickBar} />))}
          </div>
        </div>))}
      <div className="legend" style={{ marginTop: 12 }}>
        <span><span className="sw" style={{ background: 'var(--accent)' }} />Articles from the outlets we followed all year</span>
        <span><span className="sw" style={{ background: 'var(--ink-2)', height: 2, verticalAlign: 3 }} />Usual level for {need.usual}</span>
        <span><span className="ramp" style={{ marginRight: 5 }}>{[2, 3, 4, 5, 6].map((i) => <span key={i} style={{ background: `var(--gap-${i})` }} />)}</span>Last 4 weeks fell clearly short</span>
        <span><span className="sw" style={{ background: 'var(--gap-0)', boxShadow: 'inset 0 0 0 1px var(--line)' }} />About as usual</span>
        <span><svg width="14" height="12" style={{ verticalAlign: -2, marginRight: 5 }}><HatchDefs id="tb-hatch-legend" /><rect width="14" height="12" rx="2" fill="url(#tb-hatch-legend)" /></svg>Not judged</span>
        <span><span className="sw" style={{ border: '1px dashed var(--accent)', background: 'none' }} />This week, still coming in</span>
      </div>
    </div>
  )
}
