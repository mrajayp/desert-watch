// Words and scales for the Trends bars (charts/TrendBars.jsx), kept free of JSX so
// scripts/trends.test.mjs can check them with node --test.
import * as d3 from 'd3'
import { fmt } from './scales.js'

// per lens: the need in the tooltip, the usual-level phrase, and the words when a theme has none
export const LENS_NEED = {
  audience: { label: 'Wikipedia views', usual: 'this much reader interest', none: 'No reader data linked to this theme', short: 'No reader data' },
  events: { label: 'Conflict and protest events', usual: 'this many events', none: 'No event data linked to this theme', short: 'No event data' },
  humanitarian: { label: 'ReliefWeb reports', usual: 'this many ReliefWeb reports', none: 'No ReliefWeb reports linked to this theme', short: 'No ReliefWeb data' },
  journalist: { label: 'Gaps flagged by the team', usual: 'this many team flags', none: 'No team flags on this theme', short: 'No team flags' },
}
export const lensNeed = (lens) => LENS_NEED[lens] || LENS_NEED.audience

// why a week is not judged: [pill, sentence]. too_few_expected is about the usual level (under 3
// articles for the reader data we have), not about how many articles the theme got.
const REASONS = {
  too_few_expected: ['Usual level too low to judge', 'The usual level is too low to judge'],
  building_baseline: ['Still building a baseline', 'We are still building a baseline for this theme'],
  in_progress: ['Still coming in', 'This week is still coming in'],
}
export const reasonText = (reason, need, long) => (reason === 'no_need_data' ? (long ? need.none : need.short)
  : (REASONS[reason] || ['Not scored yet', 'Not scored yet'])[long ? 1 : 0])

const times = (g) => { const x = Math.exp(g); return x >= 10 ? String(Math.round(x)) : x.toFixed(1) }
// red_from either way: clearly fewer (red on the page), clearly more (neutral), or about as usual
export const shortfall = (g, red) => (g >= red ? `About ${times(g)} times fewer articles than usual`
  : g <= -red ? `About ${times(-g)} times more articles than usual` : 'About as usual')
export const articles = (n) => `${fmt(n)} article${n === 1 ? '' : 's'}`
// one decimal under 10, so a usual level of 2.7 does not read as the 3-article minimum
export const about = (v) => (v >= 10 ? `about ${fmt(v)}` : v >= 1 ? `about ${+v.toFixed(1)}` : 'less than 1')
export const judged = (r) => !r.in_progress && !r.insufficient && r.gap != null

// the 4-week verdict for the week ending a row, as one or two sentences
export function verdict(r, red, need) {
  if (r.in_progress) return 'This week is still coming in. Not judged yet.'
  if (r.reason === 'too_few_expected' && r.articles_4w != null && r.expected_4w != null) {
    return `Last 4 weeks: ${articles(r.articles_4w)} against ${about(r.expected_4w)} usual. The usual level is too low to judge.`
  }
  if (!judged(r)) return `Last 4 weeks: not judged. ${reasonText(r.reason, need, true)}.`
  return `Last 4 weeks: ${articles(r.articles_4w)} against ${about(r.expected_4w)} usual. ${shortfall(r.gap, red)}.`
}

// the lens need for one week, in its unit (Wikipedia views split by language)
export function needLine(r, need, lens) {
  if (r.need_week == null) return null
  const so = r.in_progress ? ' so far' : ''
  const split = lens === 'audience' && r.need_en != null ? ` (English ${fmt(r.need_en)}, Arabic ${fmt(r.need_ar)})` : ''
  const trimmed = r.need_week_raw > r.need_week + 0.5 ? ` Before we trimmed one-day spikes: ${fmt(r.need_week_raw)}.` : ''
  return `${need.label}${so}: ${fmt(r.need_week)}${split}.${trimmed}`
}

export const DAY = 864e5
export const utc = (s) => new Date(s + 'T00:00:00Z')
export const weekEnd = (w) => new Date(utc(w).getTime() + 6 * DAY).toISOString().slice(0, 10)
export function weekRange(w) {
  const a = utc(w), b = new Date(a.getTime() + 6 * DAY), f = d3.utcFormat
  if (a.getUTCFullYear() !== b.getUTCFullYear()) return `${f('%-d %b %Y')(a)} to ${f('%-d %b %Y')(b)}`
  if (a.getUTCMonth() !== b.getUTCMonth()) return `${f('%-d %b')(a)} to ${f('%-d %b %Y')(b)}`
  return `${f('%-d')(a)} to ${f('%-d %b %Y')(b)}`
}

// linear from 0 with 3-4 labelled gridlines (0 included) ending on the top of the domain
export function yScale(top, range) {
  for (const n of [3, 2, 4]) {
    const hi = d3.nice(0, top, n)[1]
    const ticks = d3.ticks(0, hi, n)
    if (ticks.length >= 3 && ticks.length <= 4 && ticks[ticks.length - 1] === hi) return [d3.scaleLinear().domain([0, hi]).range(range), ticks]
  }
  const y = d3.scaleLinear().domain([0, top]).nice(3).range(range)
  return [y, y.ticks(3)]
}

// The usual level, one value per row. Each week's step is its own expected_week (that week's need at
// its own baseline). The 4 weeks of the window in focus (the hovered week, else the latest complete one)
// are drawn at the focus week's baseline instead, so those 4 steps add up to the usual level its verdict
// quotes (expected_4w). Baselines move, so 4 steps drawn each at their own would only roughly add up.
// No step on the week still coming in: its need covers only part of the week.
export function usualLine(rows, focus, hasNeed) {
  if (!hasNeed) return rows.map(() => null)
  const f = rows[focus]
  const ok = f && !f.in_progress && f.ref != null && f.expected_4w != null
  return rows.map((r, i) => {
    if (r.in_progress) return null
    if (ok && i <= focus && i > focus - 4 && r.need_week != null) return r.need_week * f.ref
    return r.expected_week ?? null
  })
}

// the usual level as a step path: one flat segment per week, broken where `value` is null
export function stepPath(rows, x, step, y, value) {
  let path = '', open = false
  for (const [i, r] of rows.entries()) {
    const v = value(r, i)
    if (v == null) { open = false; continue }
    const x0 = x(r.week), yy = y(v).toFixed(1)
    path += `${open ? `V${yy}` : `M${x0.toFixed(1)},${yy}`}H${(x0 + step).toFixed(1)}`
    open = true
  }
  return path
}
