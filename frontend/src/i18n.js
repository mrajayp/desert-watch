// Interface language: English or Arabic. Code is written in English and every visible string goes
// through t() (or tn() for counts). The Arabic catalogue lives in locales/ar/*.js, keyed by the exact
// English text, so an untranslated string shows in English rather than breaking.
//   t('Sign out')                       -> 'تسجيل الخروج'
//   t('{n} articles in {week}', {n, week})
//   tn(n, '{n} article', '{n} articles') -> Arabic entry for '{n} articles' may be a string or an
//                                           object of plural forms {zero, one, two, few, many, other}
//   pick(theme, 'name')                 -> theme.name_ar in Arabic, theme.name_en otherwise
// scripts/check-i18n.mjs fails the build when a visible string is not wrapped or has no Arabic.
import { timeFormatLocale } from 'd3-time-format'
import AR from './locales/ar/index.js'

export const LANGS = ['en', 'ar']
let current = 'en'

export function getLang() { return current }
export const isAr = () => current === 'ar'

export function setLang(l) {
  current = l === 'ar' ? 'ar' : 'en'
  if (typeof document !== 'undefined') {
    document.documentElement.lang = current
    document.documentElement.dir = current === 'ar' ? 'rtl' : 'ltr'
  }
  return current
}

// first visit: the saved choice, else the browser's language
export function initialLang() {
  try {
    const saved = localStorage.getItem('dw_lang')
    if (saved === 'ar' || saved === 'en') return saved
  } catch { /* storage blocked */ }
  const nav = typeof navigator !== 'undefined' ? (navigator.languages || [navigator.language || '']) : []
  return nav.some((x) => /^ar\b/i.test(x || '')) ? 'ar' : 'en'
}

export function saveLang(l) { try { localStorage.setItem('dw_lang', l) } catch { /* storage blocked */ } }

const fill = (s, vars) => (vars ? String(s).replace(/\{(\w+)\}/g, (m, k) => (vars[k] ?? m)) : String(s))
const plural = typeof Intl !== 'undefined' && Intl.PluralRules ? new Intl.PluralRules('ar') : null

export function t(en, vars) {
  if (current === 'ar') {
    const a = AR[en]
    if (typeof a === 'string') return fill(a, vars)
    if (a && typeof a === 'object') {
      const form = vars && vars.n != null && plural ? plural.select(Number(vars.n)) : 'other'
      return fill(a[form] ?? a.other, vars)
    }
  }
  return fill(en, vars)
}

// marks a string in a module-level table for the catalogue; translate it with t() when rendering
export const N_ = (s) => s

export function tn(n, one, other, vars = {}) {
  const v = { ...vars, n }
  if (current === 'ar') return t(other, v)
  return fill(n === 1 ? one : other, v)
}

// a bilingual field from API data (name_en / name_ar, label / label_ar, title / title_ar ...)
export function pick(o, base = 'name') {
  if (!o) return ''
  const en = o[`${base}_en`] ?? o[base]
  return current === 'ar' ? (o[`${base}_ar`] || en || '') : (en || o[`${base}_ar`] || '')
}

// Western digits with a dot for decimals, as Libyan media write prices (10.22 دينار); month names
// يناير ... ديسمبر. (ar-LY would write 1.234,5: a dot for thousands, easily read as a decimal.)
export const locale = () => (current === 'ar' ? 'ar-u-nu-latn' : 'en-GB')

// an API date or timestamp as a Date: a day (YYYY-MM-DD) and a timestamp with no zone are UTC
const asDate = (d) => {
  if (d instanceof Date) return d
  const s = String(d).trim().replace(' ', 'T')
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return new Date(`${s}T00:00:00Z`)
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/.test(s)) return new Date(`${s}Z`)
  return new Date(s)
}

export function fmtDate(d, opts = { day: 'numeric', month: 'short', year: 'numeric' }) {
  if (d == null || d === '') return ''
  const date = asDate(d)
  if (Number.isNaN(+date)) return String(d)
  return new Intl.DateTimeFormat(locale(), { timeZone: 'UTC', ...opts }).format(date)
}
// a timestamp as "17 Oct 2026, 14:05" (UTC, 24-hour clock)
export const fmtDateTime = (d) => fmtDate(d, { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false })
// a month ("2026-10", or any day in it) as "Oct 2026"
export const fmtMonth = (d) => fmtDate(typeof d === 'string' && /^\d{4}-\d{2}$/.test(d.trim()) ? `${d.trim()}-01` : d, { month: 'short', year: 'numeric' })

export function fmtNum(n, opts) {
  return n == null ? '' : new Intl.NumberFormat(locale(), opts).format(n)
}

const MONTHS_AR = ['يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو', 'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر']
const DAYS_AR = ['الأحد', 'الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت']
const D3_AR = timeFormatLocale({
  dateTime: '%A، %e %B %Y، %X', date: '%d/%m/%Y', time: '%H:%M:%S', periods: ['ص', 'م'],
  days: DAYS_AR, shortDays: DAYS_AR, months: MONTHS_AR, shortMonths: MONTHS_AR,
})
const D3_EN = timeFormatLocale({
  dateTime: '%a %e %b %Y %X', date: '%d/%m/%Y', time: '%H:%M:%S', periods: ['AM', 'PM'],
  days: ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'],
  shortDays: ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'],
  months: ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'],
  shortMonths: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'],
})
// d3.utcFormat in the interface language, for chart axes and tooltips
export const utcFormat = (spec) => (current === 'ar' ? D3_AR : D3_EN).utcFormat(spec)
