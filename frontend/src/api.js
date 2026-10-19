// Thin fetch wrapper + the behaviour tracker (batched, first-party only).
// Every request says which interface language is on (X-Lang), so the server answers in it.
// Failures are always an ApiError: status 0 = no connection, 401 = signed out (the app's handler
// clears the user and sends it to the sign-in page), anything else = the server's message.
// An aborted request (AbortController) rejects with the browser's AbortError, never an ApiError,
// so a hook can tell a cancelled call from a failed one.
import { getLang, t } from './i18n.js'

export class ApiError extends Error {
  constructor(status, message) { super(message); this.name = 'ApiError'; this.status = status } // i18n-ok: an error class name, not shown
}

export const isAbort = (e) => e?.name === 'AbortError'

// Set by the app: called with the path when any call but the sign-in and the first /api/me gets a 401.
let onUnauthorised = null
export function setUnauthorisedHandler(fn) { onUnauthorised = fn }

// ---- the GET memo ------------------------------------------------------------------------------
// /api/cells and /api/network answers are kept for 10 minutes, keyed by URL and interface language:
// the past weeks they describe change only at the :45 recompute, and the week slider, "play" and a
// page change ask for the same URLs again and again. An in-flight call is shared too. refresh()
// (a vote, a claim, an added article) calls invalidateMemo() so the next GET goes to the server;
// `fresh: true` on one call does the same for that call. Failures are never kept.
export const MEMO_PATHS = [/^\/api\/cells(\?|$)/, /^\/api\/network(\?|$)/]
export const MEMO_MS = 10 * 60 * 1000
const memo = new Map() // key -> { at, promise }
let now = () => Date.now()
export const isMemoable = (path, method = 'GET') => method === 'GET' && MEMO_PATHS.some((re) => re.test(path))
export function invalidateMemo() { memo.clear() }
export const memoSize = () => memo.size
// tests: a fake clock
export function _setClock(fn) { now = fn || (() => Date.now()) }

// a shared promise rejected early for one caller when its signal fires, without cancelling the fetch
function withSignal(p, signal) {
  if (!signal || typeof signal.addEventListener !== 'function') return p
  return new Promise((resolve, reject) => {
    const abort = () => { const e = new Error('The operation was aborted'); e.name = 'AbortError'; reject(e) } // i18n-ok: the browser's own error name and text, never shown
    if (signal.aborted) { abort(); return }
    signal.addEventListener('abort', abort, { once: true })
    p.then((v) => { signal.removeEventListener('abort', abort); resolve(v) }, (e) => { signal.removeEventListener('abort', abort); reject(e) })
  })
}

// silent401: the caller expects "not signed in" as an answer (the first /api/me) and handles it itself
// fresh: skip the memo for this call (the answer still refreshes it)
export async function api(path, { method = 'GET', body, signal, silent401 = false, fresh = false } = {}) {
  if (isMemoable(path, method)) {
    const key = `${getLang()} ${path}`
    const hit = memo.get(key)
    if (hit && !fresh && now() - hit.at < MEMO_MS) return withSignal(hit.promise, signal)
    const promise = request(path, { method, body, silent401 })
    memo.set(key, { at: now(), promise })
    promise.catch(() => { if (memo.get(key)?.promise === promise) memo.delete(key) })
    return withSignal(promise, signal)
  }
  return request(path, { method, body, signal, silent401 })
}

async function request(path, { method = 'GET', body, signal, silent401 = false } = {}) {
  let r
  try {
    r = await fetch(path, {
      method, signal, credentials: 'same-origin',
      headers: body ? { 'Content-Type': 'application/json', 'X-Lang': getLang() } : { 'X-Lang': getLang() },
      body: body ? JSON.stringify(body) : undefined,
    })
  } catch (e) {
    if (isAbort(e)) throw e
    throw new ApiError(0, t('No connection'))
  }
  if (!r.ok) {
    let msg = r.statusText
    try { const j = await r.json(); msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail) } catch { /* not json */ }
    if (r.status === 401 && !silent401 && path !== '/api/auth/login' && onUnauthorised) onUnauthorised(path)
    throw new ApiError(r.status, msg || t('Request failed'))
  }
  return r.status === 204 ? null : r.json()
}

export const qs = (o) => '?' + new URLSearchParams(Object.entries(o).filter(([, v]) => v !== undefined && v !== null && v !== '')).toString()

// ---- tracker -------------------------------------------------------------
// Implicit events (views, clicks, dwell) are sent for every user; there is no opt-out
// (owner decision 2026-10-13). Explicit actions are logged server-side by the endpoints.
const SESSION = (() => {
  try {
    let s = sessionStorage.getItem('dw_sid')
    if (!s) { s = Math.random().toString(36).slice(2) + Date.now().toString(36); sessionStorage.setItem('dw_sid', s) }
    return s
  } catch { return 'nostorage' }
})()

let queue = []
let enabled = false
let timer = null

export function setTracking(on) { enabled = on; if (!on) queue = [] }

export function track(type, object_type, object_key, context = {}) {
  if (!enabled) return
  queue.push({ type, object_type, object_key: object_key == null ? null : String(object_key), context })
  if (queue.length >= 25) flush()
  else if (!timer) timer = setTimeout(flush, 5000)
}

export function flush() {
  clearTimeout(timer); timer = null
  if (!queue.length) return
  const events = queue; queue = []
  const body = JSON.stringify({ session_id: SESSION, events })
  if (navigator.sendBeacon && document.visibilityState === 'hidden') {
    navigator.sendBeacon('/api/events', new Blob([body], { type: 'application/json' }))
  } else {
    fetch('/api/events', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body }).catch(() => {})
  }
}
if (typeof window !== 'undefined') {
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') flush() })
}

// Dwell tracker: call start() when a gap/item is shown, stop() returns seconds and logs a dwell event.
export function dwell(object_type, object_key, context = {}) {
  const t0 = performance.now()
  return () => {
    const seconds = Math.round((performance.now() - t0) / 100) / 10
    if (seconds >= 2) track('dwell', object_type, object_key, { ...context, seconds })
  }
}
