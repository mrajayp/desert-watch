// Words and scales for the Trends bars (charts/TrendBars.jsx), kept free of JSX so
// scripts/trends.test.mjs can check them with node --test.
import * as d3 from 'd3'
import { fmt } from './scales.js'
import { t, tn, utcFormat } from '../i18n.js'

// marks a string for the Arabic catalogue where a table is defined; t() translates it when it is shown
const N_ = (s) => s

// per lens: the need in the tooltip, the level phrase, the words when a theme has none and, on the
// lenses with a need floor, the words when 4 weeks have too little need to judge ([pill, sentence]).
// The pill words are short and lower-case: they follow "Not judged ·".
export const LENS_NEED = {
  audience: { label: N_('Wikipedia views'), usual: N_('this much reader interest'), none: N_('No reader data linked to this theme'), short: N_('no reader data') },
  events: { label: N_('Conflict and protest events'), usual: N_('this many events'), none: N_('No event data linked to this theme'), short: N_('no event data'),
    few: [N_('too few events'), N_('There were too few events to judge')] },
  humanitarian: { label: N_('ReliefWeb reports'), usual: N_('this many ReliefWeb reports'), none: N_('No ReliefWeb reports linked to this theme'), short: N_('no ReliefWeb data'),
    few: [N_('too few reports'), N_('There were too few ReliefWeb reports to judge')] },
  journalist: { label: N_('Gaps flagged by the team'), usual: N_('this many team flags'), none: N_('No team flags on this theme'), short: N_('no team flags'),
    few: [N_('too few team flags'), N_('There were too few team flags to judge')] },
  search: { label: N_('Google searches (index)'), usual: N_('this much search interest'), none: N_('Too few searches in Libya to compare'), short: N_('too few searches to compare') },
}
// reference: the lens's meta reference. A pooled lens compares a theme with what other topics get; the
// other lenses compare a theme with its own record (its usual level). Either way the level a theme is
// held to is called the expected level in the interface; "usual level" survives only in the legend
// and in "this theme's usual level", which names the own-record comparison.
export const lensNeed = (lens, reference) => {
  const need = LENS_NEED[lens] || LENS_NEED.audience
  return reference === 'pooled' ? { ...need, pooled: true } : need
}
// the grey line in the legend
export const levelLegend = (need) => (need?.pooled ? t('Expected level for {what}, going by other topics', { what: t(need.usual) })
  : t('Usual level for {what}', { what: t(need.usual) }))

// why 4 weeks are not judged: [pill words, sentence]. too_few_expected is about the expected level
// (under 3 articles for the reader data we have), not about how many articles the theme got.
const REASONS = {
  too_few_expected: [N_('expected level too low'), N_('The expected level is too low to judge')],
  too_little_need: [N_('too little data'), N_('There was too little data to judge')],
  no_search_data: [N_('no search data for a week'), N_('Google gave no search data for one of these 4 weeks')],
  building_baseline: [N_('still building a baseline'), N_('We are still building a baseline for this theme')],
  in_progress: [N_('still coming in'), N_('This week is still coming in')],
}
// '' for a reason code this file does not know: the pill then says only "Not judged"
export function reasonText(reason, need, long) {
  const i = long ? 1 : 0
  if (reason === 'no_need_data') return t(long ? need.none : need.short)
  if (reason === 'too_little_need' && need.few) return t(need.few[i])
  return REASONS[reason] ? t(REASONS[reason][i]) : ''
}
// the pill on a theme that could not be judged: "Not judged · too few events"
export function notJudged(reason, need) {
  const why = reasonText(reason, need, false)
  return why ? t('Not judged · {reason}', { reason: why }) : t('Not judged')
}

const times = (g) => { const x = Math.exp(g); return x >= 10 ? String(Math.round(x)) : x.toFixed(1) }
// red_from either way: clearly fewer (red on the page), clearly more (neutral), or about as expected
export function shortfall(g, red) {
  return g >= red ? t('About {x} times fewer articles than expected', { x: times(g) })
    : g <= -red ? t('About {x} times more articles than expected', { x: times(-g) }) : t('About as expected')
}
export const articles = (n) => tn(n, '{num} article', '{num} articles', { num: fmt(n) }) // not {count}: overview.js has '{count} articles' as a plain label
// one decimal under 10, so an expected level of 2.7 does not read as the 3-article minimum
export const about = (v) => (v >= 10 ? t('about {n}', { n: fmt(v) }) : v >= 1 ? t('about {n}', { n: +v.toFixed(1) }) : t('less than 1'))
export const judged = (r) => !r.in_progress && !r.insufficient && r.gap != null
const against = (r, need) => (need?.pooled
  ? t('{articles} against {about} expected from other topics', { articles: articles(r.articles_4w), about: about(r.expected_4w) })
  : t('{articles} against {about} expected from this theme’s usual level', { articles: articles(r.articles_4w), about: about(r.expected_4w) }))

// the 4-week verdict for the week ending a row, as one or two sentences
export function verdict(r, red, need) {
  if (r.in_progress) return t('This week is still coming in. Not judged yet.')
  if (r.reason === 'too_few_expected' && r.articles_4w != null && r.expected_4w != null) {
    return t('Last 4 weeks: {counts}. {verdict}.', { counts: against(r, need), verdict: reasonText(r.reason, need, true) })
  }
  if (!judged(r)) {
    const why = reasonText(r.reason, need, true)
    return why ? t('Last 4 weeks: not judged. {reason}.', { reason: why }) : t('Last 4 weeks: not judged.')
  }
  return t('Last 4 weeks: {counts}. {verdict}.', { counts: against(r, need), verdict: shortfall(r.gap, red, need) })
}

// search lens: a week with no search data (not imported yet, or one Google held back). The Trends
// panels then open on the lens's latest scored week.
export const noSearchData = (r) => !r.need_week || r.reason === 'no_search_data'

// the lens need for one week, in its unit (Wikipedia views split by language)
export function needLine(r, need, lens) {
  if (r.need_week == null) return null
  const label = r.in_progress ? t('{label} so far', { label: t(need.label) }) : t(need.label)
  const line = lens === 'audience' && r.need_en != null
    ? t('{label}: {n} (English {en}, Arabic {ar}).', { label, n: fmt(r.need_week), en: fmt(r.need_en), ar: fmt(r.need_ar) })
    : `${label}: ${fmt(r.need_week)}.`
  return r.need_week_raw > r.need_week + 0.5 ? t('{line} Before we trimmed one-day spikes: {n}.', { line, n: fmt(r.need_week_raw) }) : line
}

export const DAY = 864e5
export const utc = (s) => new Date(s + 'T00:00:00Z')
export const weekEnd = (w) => new Date(utc(w).getTime() + 6 * DAY).toISOString().slice(0, 10)
export function weekRange(w) {
  const a = utc(w), b = new Date(a.getTime() + 6 * DAY), f = utcFormat
  const span = (from, to) => t('{from} to {to}', { from, to })
  if (a.getUTCFullYear() !== b.getUTCFullYear()) return span(f('%-d %b %Y')(a), f('%-d %b %Y')(b))
  if (a.getUTCMonth() !== b.getUTCMonth()) return span(f('%-d %b')(a), f('%-d %b %Y')(b))
  return span(f('%-d')(a), f('%-d %b %Y')(b))
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

// Panel groups. Most lenses: General first, then each named group (Gender). On the search lens the themes
// Google can measure come first, and the rest keep their charts under a heading that says why there is
// nothing to compare them with. Labels and the note stay English here (N_); TrendBars shows them with t().
export const SEARCH_FEW = N_('Google reports too few searches from Libya on these themes to show interest, so there is no expected level to measure their coverage against. The bars still show the articles.')
export function trendGroups(themes, data, lens) {
  const shown = themes.filter((t) => data?.themes?.[t.id]?.rows?.length)
  const byGroup = (list) => {
    const plain = list.filter((t) => !t.group)
    const named = [...new Set(list.filter((t) => t.group).map((t) => t.group))]
    return [...(plain.length ? [{ label: N_('General'), themes: plain }] : []),
      ...named.map((g) => ({ label: g[0].toUpperCase() + g.slice(1), themes: list.filter((t) => t.group === g) }))]
  }
  if (lens !== 'search') return byGroup(shown)
  const measured = shown.filter((t) => data.themes[t.id].has_need)
  const rest = shown.filter((t) => !data.themes[t.id].has_need)
  if (!measured.length || !rest.length) return byGroup(shown)
  // these headings mix groups, so panels keep the full name ("Gender: ...")
  return [{ label: N_('Enough searches to compare'), themes: measured, fullNames: true },
    { label: N_('Too few searches to compare'), themes: rest, note: SEARCH_FEW, fullNames: true }]
}
