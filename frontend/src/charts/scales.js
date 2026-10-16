// Shared encodings. Colours are CSS custom properties so light/dark swap in one place.
export const css = (name) => `var(--${name})`

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
export function gapLabel(g) {
  if (g == null) return 'insufficient evidence'
  const x = Math.exp(g)
  if (g < 0.15) return 'covered about as expected or more'
  return `about ${x >= 10 ? Math.round(x) : x.toFixed(1)}× less coverage than expected`
}

export function covFill(n, max) {
  if (!n) return css('gap-0')
  const steps = [1, 2, 3, 4, 5]
  const i = Math.min(4, Math.floor((Math.log1p(n) / Math.log1p(Math.max(max, 1))) * 5))
  return css(`cov-${steps[i]}`)
}

export const DIMENSIONS = {
  scope: {
    label: 'Scope',
    values: { libyan: 'Libyan', international: 'International', diaspora: 'Diaspora', unknown: 'Unclassified' },
    colors: { libyan: 'scope-libyan', international: 'scope-international', diaspora: 'scope-diaspora' },
  },
  alignment: {
    label: 'Political alignment',
    values: {
      tripoli_gnu_aligned: 'Tripoli / GNU-aligned', east_lna_aligned: 'East / LNA-aligned', independent: 'Independent',
      islamist_leaning: 'Islamist-leaning', tribal_local: 'Tribal / local', unknown: 'Unclassified',
    },
    colors: { tripoli_gnu_aligned: 'al-1', independent: 'al-2', east_lna_aligned: 'al-3', islamist_leaning: 'al-4', tribal_local: 'al-5' },
  },
  type: {
    label: 'Ownership type',
    values: { state: 'State', private: 'Private', public_service: 'Public service', ngo_un: 'NGO / UN', citizen_collective: 'Citizen collective', international: 'International', unknown: 'Unclassified' },
    colors: { state: 'al-3', private: 'al-1', public_service: 'al-2', ngo_un: 'al-4', citizen_collective: 'al-5', international: 'scope-international' },
  },
  language: {
    label: 'Main language',
    values: { ar: 'Arabic', en: 'English', other: 'Other', unknown: 'Unknown' },
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

export const FLAG_TEXT = {
  coverage_drop: 'Coverage dropped while need held',
  little_arabic: 'Little Arabic coverage',
  outside_only: 'Only covered from outside Libya',
  mostly_unplaced: 'Most coverage names no place',
}
export const INFO_FLAGS = new Set(['mostly_unplaced'])
export function flagText(f) {
  if (f.startsWith('partisan_only:')) return `Only ${DIMENSIONS.alignment.values[f.split(':')[1]] || 'one side'} outlets`
  return FLAG_TEXT[f] || f
}

export const LENS_TEXT = {
  audience: { label: 'Audience', unit: 'pageviews', blurb: 'Wikipedia interest vs coverage, against the theme’s own recent history (national only)' },
  events: { label: 'Events', unit: 'events', blurb: 'Conflict & protest events (ACLED/UCDP) vs coverage' },
  humanitarian: { label: 'Humanitarian', unit: 'reports', blurb: 'ReliefWeb reports vs coverage' },
  journalist: { label: 'Journalists', unit: 'flags', blurb: 'Gaps flagged by your team vs coverage' },
  search: { label: 'Libyan searches (Google)', unit: 'search index', blurb: 'Google searches from people in Libya vs coverage, against the theme’s own recent history (national only)', waiting: 'waiting for the next import of search data' },
}

export const fmt = (n) => n == null ? '–' : n >= 1e6 ? `${(n / 1e6).toFixed(n >= 1e7 ? 0 : 1)}M` : n >= 10000 ? `${(n / 1000).toFixed(n >= 100000 ? 0 : 1)}K` : Math.round(n).toLocaleString()

// Where an article came from (item.source = collector key)
export const SOURCE_LABELS = {
  galerts: 'Google Alerts', gnews: 'Google News', rss: 'Outlet RSS', gdelt: 'GDELT',
  official: 'Official / ReliefWeb', user: 'Added by team', backfill: 'Historical backfill',
  gnews_social: 'Social (Google-indexed)', youtube: 'YouTube channels',
}
export const sourceLabel = (k) => SOURCE_LABELS[k] || k
