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

// silent401: the caller expects "not signed in" as an answer (the first /api/me) and handles it itself
export async function api(path, { method = 'GET', body, signal, silent401 = false } = {}) {
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
