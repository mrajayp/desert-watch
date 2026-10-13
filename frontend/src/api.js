// Thin fetch wrapper + the behaviour tracker (batched, first-party only).

export class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status }
}

export async function api(path, { method = 'GET', body, signal } = {}) {
  const r = await fetch(path, {
    method, signal, credentials: 'same-origin',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!r.ok) {
    let msg = r.statusText
    try { const j = await r.json(); msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail) } catch { /* not json */ }
    throw new ApiError(r.status, msg)
  }
  return r.status === 204 ? null : r.json()
}

export const qs = (o) => '?' + new URLSearchParams(Object.entries(o).filter(([, v]) => v !== undefined && v !== null && v !== '')).toString()

// ---- tracker -------------------------------------------------------------
// Implicit events are sent only when the user has not opted out (the server
// enforces this too). Explicit actions are logged server-side by the endpoints.
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
