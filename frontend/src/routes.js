// The URL scheme, in one place, with no React in it (scripts/routes.test.mjs runs it in Node).
//   /                                  the map (Overview)
//   /gaps/:themeId/:regionId?lens=&week=   one gap (a dialog over the page from 900px up, a page below)
//   /articles?theme=&region=&days=&start=&end=&lang=&source=&q=&basis=   the article list
//   /articles/:id                      one article: rate, correct, discuss
//   /outlets/:id                       one outlet
//   /add?theme=&region=                add an article we missed
//   /login?next=                       sign in, then go to `next`
//   /trends /timeline /digest /contribute /admin /me /outlets /invite/:token  as before
// Page filters (lens, week, theme, colour) live in the query string of the page they apply to.
import { lensWeek } from './lensWeek.js'

export const FILTER_KEYS = ['lens', 'week', 'theme', 'colour']
const FILTER_PARAM = { lens: 'lens', week: 'week', themeId: 'theme', colorBy: 'colour' }

// "?a=1&b=2" from an object; empty, null and false values are left out
export function params(o = {}) {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(o)) if (v != null && v !== '' && v !== false) p.set(k, String(v))
  const s = p.toString()
  return s ? `?${s}` : ''
}

const DAY = /^\d{4}-\d{2}-\d{2}$/
export const isDay = (s) => DAY.test(s || '')
export const parseId = (s) => (/^\d+$/.test(s || '') ? Number(s) : null)

// ---- detail routes ---------------------------------------------------------------------------
const DETAIL = [
  ['gap', /^\/gaps\/(\d+)\/(\d+)\/?$/, '/'],
  ['article', /^\/articles\/(\d+)\/?$/, '/articles'],
  ['outlet', /^\/outlets\/(\d+)\/?$/, '/outlets'],
  ['add', /^\/add\/?$/, '/'],
]
// 'gap' | 'article' | 'outlet' | 'add' | null
export function detailKind(pathname) {
  const d = DETAIL.find(([, re]) => re.test(pathname || ''))
  return d ? d[0] : null
}
// where a detail view closes to when there is no page behind it (a shared link, a reload)
export function parentPath(pathname) {
  const d = DETAIL.find(([, re]) => re.test(pathname || ''))
  return d ? d[2] : '/'
}

export const gapPath = (themeId, regionId, { lens, week } = {}) => `/gaps/${themeId}/${regionId}${params({ lens, week })}`
export const articlePath = (id) => `/articles/${id}`
export const outletPath = (id) => `/outlets/${id}`
export const addPath = ({ theme_ids = [], region_ids = [] } = {}) => `/add${params({ theme: theme_ids.join(','), region: region_ids.join(',') })}`
export const loginPath = (next) => `/login${params({ next: next && next !== '/' ? next : '' })}`

// "1,4" -> [1, 4]
export const idList = (s) => (s || '').split(',').map(parseId).filter((x) => x != null)

// ?lens=&week= on a gap route, checked against what the app knows
export function gapParams(sp, meta) {
  const lens = sp.get('lens')
  const week = sp.get('week')
  return {
    lens: meta?.lenses?.some((l) => l.key === lens) ? lens : null,
    week: isDay(week) ? week : null,
  }
}

// ---- the article list --------------------------------------------------------------------------
// The URL uses the words a reader sees (theme, region); /api/items wants theme_id, region_id.
export const ARTICLE_PARAMS = ['theme', 'region', 'days', 'start', 'end', 'lang', 'source', 'q', 'basis']
export const DEFAULT_DAYS = 7

// an /api/items query (or a URL-shaped one) -> /articles?…
export function articlesPath(query = {}) {
  return '/articles' + params({
    theme: query.theme_id ?? query.theme, region: query.region_id ?? query.region, days: query.days,
    start: query.start, end: query.end, lang: query.lang, source: query.source, q: query.q, basis: query.basis,
  })
}

// /articles?… -> the /api/items query. A date range wins over days (as the API does); otherwise days
// defaults to a week. Bad values fall back quietly, so a mistyped link still shows a list.
export function articlesQuery(sp) {
  const g = (k) => sp.get(k) || ''
  const start = isDay(g('start')) ? g('start') : ''
  const end = isDay(g('end')) ? g('end') : ''
  const days = /^\d+$/.test(g('days')) ? Math.min(3650, Number(g('days'))) : (start || end ? '' : DEFAULT_DAYS)
  return {
    theme_id: parseId(g('theme')) ?? '', region_id: parseId(g('region')) ?? '',
    days: start || end ? '' : days, start, end,
    lang: ['ar', 'en'].includes(g('lang')) ? g('lang') : '',
    source: g('source').slice(0, 40), q: g('q').slice(0, 200), basis: g('basis') === 'trend' ? 'trend' : '',
  }
}

// ---- sign-in --------------------------------------------------------------------------------------
// only a path inside this site: never another origin, never a protocol-relative "//evil"
export function safeNext(next) {
  if (!next || typeof next !== 'string') return '/'
  if (!next.startsWith('/') || next.startsWith('//') || next.startsWith('/\\') || next.startsWith('/login')) return '/'
  return next
}

// ---- page filters ---------------------------------------------------------------------------------
// The filters of a page from its query string. A missing or unknown value falls back to the saved
// preference (lens, colour) or the app's default; the saved preference is never written here.
export function readFilters(sp, meta, prefs = {}, colours = []) {
  const avail = (meta?.lenses || []).filter((l) => l.available).map((l) => l.key)
  const want = sp.get('lens')
  const lens = avail.includes(want) ? want : avail.includes(prefs.lens) ? prefs.lens : (avail[0] || 'audience')
  const w = sp.get('week')
  const week = w && (meta?.weeks || []).includes(w) ? w : lensWeek(meta, lens)
  const th = sp.get('theme') || ''
  const themeOk = th === '' || (th.startsWith('group:') ? (meta?.themes || []).some((t) => t.group === th.slice(6))
    : (meta?.themes || []).some((t) => String(t.id) === th))
  const c = sp.get('colour')
  const colorBy = colours.includes(c) ? c : colours.includes(prefs.colorBy) ? prefs.colorBy : (colours[0] || 'scope')
  return { lens, week, themeId: themeOk ? th : '', colorBy }
}

// a patch {lens, week, themeId, colorBy} written into a copy of the query string ('' or null removes)
export function applyFilters(sp, patch) {
  const next = new URLSearchParams(sp)
  for (const [k, v] of Object.entries(patch)) {
    const name = FILTER_PARAM[k]
    if (!name) continue
    if (v == null || v === '') next.delete(name)
    else next.set(name, String(v))
  }
  return next
}

// the filter part of a query string, to carry from one page to the next ("?lens=search&week=…")
export function filterSearch(sp) {
  const next = new URLSearchParams()
  for (const k of FILTER_KEYS) { const v = sp.get(k); if (v) next.set(k, v) }
  const s = next.toString()
  return s ? `?${s}` : ''
}
