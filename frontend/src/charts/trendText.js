// Words and scales for the Trends bars (charts/TrendBars.jsx), kept free of JSX so
// scripts/trends.test.mjs can check them with node --test.
import * as d3 from 'd3'
import { fmt } from './scales.js'

// per lens: the need in the tooltip, the usual-level phrase, the words when a theme has none and,
// on the lenses with a need floor, the words when a window has too little need to judge ([pill, sentence])
export const LENS_NEED = {
  audience: { label: 'Wikipedia views', usual: 'this much reader interest', none: 'No reader data linked to this theme', short: 'No reader data' },
  events: { label: 'Conflict and protest events', usual: 'this many events', none: 'No event data linked to this theme', short: 'No event data',
    few: ['Too few events to judge', 'There were too few events to judge'] },
  humanitarian: { label: 'ReliefWeb reports', usual: 'this many ReliefWeb reports', none: 'No ReliefWeb reports linked to this theme', short: 'No ReliefWeb data',
    few: ['Too few reports to judge', 'There were too few ReliefWeb reports to judge'] },
  journalist: { label: 'Gaps flagged by the team', usual: 'this many team flags', none: 'No team flags on this theme', short: 'No team flags',
    few: ['Too few team flags to judge', 'There were too few team flags to judge'] },
  search: { label: 'Google searches (index)', usual: 'this much search interest', none: 'We do not measure searches for this theme', short: 'Searches not measured' },
}
// reference: the lens's meta reference. A pooled lens compares a theme with what other topics get, so its
// level is the expected one. The other lenses compare a theme with its own record, its usual level.
export const lensNeed = (lens, reference) => {
  const need = LENS_NEED[lens] || LENS_NEED.audience
  return reference === 'pooled' ? { ...need, pooled: true } : need
}
export const levelWord = (need) => (need?.pooled ? 'expected' : 'usual')
// the grey line in the legend
export const levelLegend = (need) => (need?.pooled ? `Expected level for ${need.usual}, going by other topics` : `Usual level for ${need.usual}`)

// why a week is not judged: [pill, sentence]. too_few_expected is about the usual level (under 3
// articles for the reader data we have), not about how many articles the theme got.
const REASONS = {
  too_few_expected: ['Usual level too low to judge', 'The usual level is too low to judge'],
  too_little_need: ['Too little data to judge', 'There was too little data to judge'],
  no_search_data: ['No search data for a week', 'Google gave no search data for one of these 4 weeks'],
  building_baseline: ['Still building a baseline', 'We are still building a baseline for this theme'],
  in_progress: ['Still coming in', 'This week is still coming in'],
}
const POOLED_REASONS = {
  too_few_expected: ['Expected level too low to judge', 'The expected level is too low to judge'],
}
export function reasonText(reason, need, long) {
  const i = long ? 1 : 0
  if (reason === 'no_need_data') return long ? need.none : need.short
  if (reason === 'too_little_need' && need.few) return need.few[i]
  return ((need.pooled && POOLED_REASONS[reason]) || REASONS[reason] || ['Not scored yet', 'Not scored yet'])[i]
}

const times = (g) => { const x = Math.exp(g); return x >= 10 ? String(Math.round(x)) : x.toFixed(1) }
// red_from either way: clearly fewer (red on the page), clearly more (neutral), or about as usual
// (as expected on a pooled lens)
export function shortfall(g, red, need) {
  const w = levelWord(need)
  return g >= red ? `About ${times(g)} times fewer articles than ${w}`
    : g <= -red ? `About ${times(-g)} times more articles than ${w}` : `About as ${w}`
}
export const articles = (n) => `${fmt(n)} article${n === 1 ? '' : 's'}`
// one decimal under 10, so a usual level of 2.7 does not read as the 3-article minimum
export const about = (v) => (v >= 10 ? `about ${fmt(v)}` : v >= 1 ? `about ${+v.toFixed(1)}` : 'less than 1')
export const judged = (r) => !r.in_progress && !r.insufficient && r.gap != null
const against = (r, need) => `${articles(r.articles_4w)} against ${about(r.expected_4w)} ${need?.pooled ? 'expected from other topics' : 'usual'}`

// the 4-week verdict for the week ending a row, as one or two sentences
export function verdict(r, red, need) {
  if (r.in_progress) return 'This week is still coming in. Not judged yet.'
  if (r.reason === 'too_few_expected' && r.articles_4w != null && r.expected_4w != null) {
    return `Last 4 weeks: ${against(r, need)}. ${reasonText(r.reason, need, true)}.`
  }
  if (!judged(r)) return `Last 4 weeks: not judged. ${reasonText(r.reason, need, true)}.`
  return `Last 4 weeks: ${against(r, need)}. ${shortfall(r.gap, red, need)}.`
}

// search lens: a week with no search data (not imported yet, or one Google held back). The Trends
// panels then open on the lens's latest scored week.
export const noSearchData = (r) => !r.need_week || r.reason === 'no_search_data'

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
