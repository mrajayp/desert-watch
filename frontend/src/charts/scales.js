// Shared encodings. Colours are CSS custom properties so light/dark swap in one place.
import { fmtNum, t } from '../i18n.js'

const N_ = (s) => s // marks English for the catalogue; translated with t() when read

export const css = (name) => `var(--${name})`

// The label tables below keep the English (marked with N_) and translate when a property is read,
// so DIMENSIONS.scope.values.libyan or LENS_TEXT.audience.label is always in the interface language.
const lazy = (o) => Object.defineProperties({}, Object.fromEntries(
  Object.entries(o).map(([k, en]) => [k, { enumerable: true, get: () => t(en) }])))

// Gap (ln of expected/actual coverage): 0 = as expected. Only under-coverage is coloured;
// over-coverage stays neutral (the tool is about deserts, not surpluses).
export const GAP_BINS = [0.15, 0.4, 0.7, 1.0, 1.5, 2.2]
export function gapFill(cell) {
  if (!cell || cell.insufficient || cell.gap == null) return null
  const g = cell.gap
  let i = 0
  while (i < GAP_BINS.length && g >= GAP_BINS[i]) i++
  return css(`gap-${i}`)
}
// a number with exactly d decimals and no grouping, in the interface language's digits and decimal mark
const fixed = (v, d) => fmtNum(v, { minimumFractionDigits: d, maximumFractionDigits: d, useGrouping: false })
export function gapLabel(g) {
  if (g == null) return t('insufficient evidence')
  const x = Math.exp(g)
  if (g < 0.15) return t('covered about as expected or more')
  return t('about {x}× less coverage than expected', { x: x >= 10 ? fixed(Math.round(x), 0) : fixed(x, 1) })
}

export function covFill(n, max) {
  if (!n) return css('gap-0')
  const steps = [1, 2, 3, 4, 5]
  const i = Math.min(4, Math.floor((Math.log1p(n) / Math.log1p(Math.max(max, 1))) * 5))
  return css(`cov-${steps[i]}`)
}

export const DIMENSIONS = {
  scope: {
    get label() { return t('Scope') },
    values: lazy({ libyan: N_('Libyan'), international: N_('International'), diaspora: N_('Diaspora'), unknown: N_('Unclassified') }),
    colors: { libyan: 'scope-libyan', international: 'scope-international', diaspora: 'scope-diaspora' },
  },
  alignment: {
    get label() { return t('Political alignment') },
    values: lazy({
      tripoli_gnu_aligned: N_('Tripoli / GNU-aligned'), east_lna_aligned: N_('East / LNA-aligned'), independent: N_('Independent'),
      islamist_leaning: N_('Islamist-leaning'), tribal_local: N_('Tribal / local'), unknown: N_('Unclassified'),
    }),
    colors: { tripoli_gnu_aligned: 'al-1', independent: 'al-2', east_lna_aligned: 'al-3', islamist_leaning: 'al-4', tribal_local: 'al-5' },
  },
  type: {
    get label() { return t('Ownership type') },
    values: lazy({ state: N_('State'), private: N_('Private'), public_service: N_('Public service'), ngo_un: N_('NGO / UN'), citizen_collective: N_('Citizen collective'), international: N_('International'), unknown: N_('Unclassified') }),
    colors: { state: 'al-3', private: 'al-1', public_service: 'al-2', ngo_un: 'al-4', citizen_collective: 'al-5', international: 'scope-international' },
  },
  language: {
    get label() { return t('Main language') },
    values: lazy({ ar: N_('Arabic'), en: N_('English'), other: N_('Other'), unknown: N_('Unknown') }),
    colors: { ar: 'scope-libyan', en: 'scope-international', other: 'scope-diaspora' },
  },
}

export function categoryOf(node, dim) {
  if (dim === 'language') {
    const l = (node.languages || [])[0]
    return l === 'ar' || l === 'en' ? l : l ? 'other' : 'unknown'
  }
  return node.categories?.[dim] || 'unknown'
}
export function categoryColor(dim, value) {
  const c = DIMENSIONS[dim]?.colors?.[value]
  return c ? css(c) : css('cat-unknown')
}

export const FLAG_TEXT = lazy({
  coverage_drop: N_('Coverage dropped while need held'),
  little_arabic: N_('Little Arabic coverage'),
  outside_only: N_('Only covered from outside Libya'),
  mostly_unplaced: N_('Most coverage names no place'),
  need_incomplete: N_('Need data stops before the week ends'),
})
export const INFO_FLAGS = new Set(['mostly_unplaced', 'need_incomplete'])
export function flagText(f) {
  if (f.startsWith('partisan_only:')) { // i18n-ok: a flag code, never shown
    return t('Only {side} outlets', { side: DIMENSIONS.alignment.values[f.split(':')[1]] || t('one side') })
  }
  return FLAG_TEXT[f] || f
}

export const LENS_TEXT = {
  audience: lazy({ label: N_('International readers (Wikipedia)'), unit: N_('pageviews'), blurb: N_('Worldwide page views of the Wikipedia articles we picked for each theme, against the theme’s own recent record. Most views are of English pages, and the readers can be anywhere') }),
  events: lazy({ label: N_('Events'), unit: N_('events'), blurb: N_('Conflict & protest events (ACLED/UCDP) vs coverage') }),
  humanitarian: lazy({ label: N_('Humanitarian'), unit: N_('reports'), blurb: N_('ReliefWeb reports vs coverage') }),
  journalist: lazy({ label: N_('Journalists'), unit: N_('flags'), blurb: N_('Gaps flagged by your team vs coverage') }),
  search: lazy({ label: N_('Libyan searches (Google)'), unit: N_('search index'), blurb: N_('Google searches from people in Libya vs coverage, against the theme’s own recent history (national only)'), waiting: N_('waiting for the next import of search data') }),
}

export const fmt = (n) => n == null ? '–' : n >= 1e6 ? t('{n}M', { n: fixed(n / 1e6, n >= 1e7 ? 0 : 1) }) : n >= 10000 ? t('{n}K', { n: fixed(n / 1000, n >= 100000 ? 0 : 1) }) : fmtNum(Math.round(n))

// Where an article came from (item.source = collector key)
export const SOURCE_LABELS = lazy({
  galerts: N_('Google Alerts'), gnews: N_('Google News'), rss: N_('Outlet RSS'), gdelt: 'GDELT',
  official: N_('Official / ReliefWeb'), user: N_('Added by team'), backfill: N_('Historical backfill'),
  gnews_social: N_('Social (Google-indexed)'), youtube: N_('YouTube channels'),
})
export const sourceLabel = (k) => SOURCE_LABELS[k] || k
