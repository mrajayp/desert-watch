// The API client's error mapping, with a mocked fetch. Run: npm test (node --test).
//   a failed answer  -> ApiError(status, the server's detail)
//   no network       -> ApiError(0, 'No connection')
//   an aborted call  -> the browser's AbortError, untouched
//   a 401            -> the app's handler, except on sign-in and on a call marked silent401
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { ApiError, api, isAbort, setUnauthorisedHandler } from '../src/api.js'

const reply = (status, body, { ok = status < 400, statusText = '' } = {}) => ({
  ok, status, statusText,
  json: async () => { if (body === undefined) throw new Error('not json'); return body },
})
let calls = []
const mockFetch = (answer) => {
  calls = []
  globalThis.fetch = async (path, init) => { calls.push({ path, init }); return typeof answer === 'function' ? answer(path, init) : answer }
}

test('a good answer is its JSON; 204 is null; every call carries X-Lang and same-origin credentials', async () => {
  mockFetch(reply(200, { ok: 1 }))
  assert.deepEqual(await api('/api/meta'), { ok: 1 })
  assert.equal(calls[0].init.headers['X-Lang'], 'en')
  assert.equal(calls[0].init.credentials, 'same-origin')
  mockFetch(reply(204, undefined))
  assert.equal(await api('/api/x', { method: 'DELETE' }), null)
})

test('a failed answer is an ApiError with the status and the server detail', async () => {
  mockFetch(reply(400, { detail: 'Needs a link' }))
  const e = await api('/api/gap/vote', { method: 'POST', body: { vote: 'covered' } }).catch((x) => x)
  assert.ok(e instanceof ApiError)
  assert.equal(e.name, 'ApiError')
  assert.equal(e.status, 400)
  assert.equal(e.message, 'Needs a link')
  assert.equal(calls[0].init.headers['Content-Type'], 'application/json')
  assert.equal(calls[0].init.body, JSON.stringify({ vote: 'covered' }))
})

test('a structured detail is kept as JSON text; a non-JSON body falls back to the status text, then a generic message', async () => {
  mockFetch(reply(422, { detail: [{ loc: ['body', 'week'], msg: 'invalid date' }] }))
  const e = await api('/api/x').catch((x) => x)
  assert.equal(e.status, 422)
  assert.match(e.message, /invalid date/)
  mockFetch(reply(502, undefined, { statusText: 'Bad Gateway' }))
  assert.equal((await api('/api/x').catch((x) => x)).message, 'Bad Gateway')
  mockFetch(reply(500, undefined, { statusText: '' }))
  assert.equal((await api('/api/x').catch((x) => x)).message, 'Request failed')
})

test('a network failure (fetch rejects with a TypeError) becomes ApiError(0, "No connection")', async () => {
  mockFetch(() => { throw new TypeError('Failed to fetch') })
  const e = await api('/api/cells').catch((x) => x)
  assert.ok(e instanceof ApiError)
  assert.equal(e.status, 0)
  assert.equal(e.message, 'No connection')
})

test('an aborted call rejects with the AbortError itself, never an ApiError', async () => {
  const abort = new Error('The operation was aborted')
  abort.name = 'AbortError'
  mockFetch(() => { throw abort })
  const e = await api('/api/cells', { signal: {} }).catch((x) => x)
  assert.equal(e, abort)
  assert.ok(isAbort(e))
  assert.ok(!(e instanceof ApiError))
})

test('a 401 calls the unauthorised handler with the path, but not for sign-in or a silent401 call', async () => {
  const seen = []
  setUnauthorisedHandler((path) => seen.push(path))
  try {
    mockFetch(reply(401, { detail: 'Session expired' }))
    const e = await api('/api/gap?theme_id=1').catch((x) => x)
    assert.equal(e.status, 401)
    assert.equal(e.message, 'Session expired')
    assert.deepEqual(seen, ['/api/gap?theme_id=1'])
    await api('/api/auth/login', { method: 'POST', body: { email: 'a@b.c', password: 'x' } }).catch(() => {})
    await api('/api/me', { silent401: true }).catch(() => {})
    assert.deepEqual(seen, ['/api/gap?theme_id=1'])
    // other failures never touch the handler
    mockFetch(reply(403, { detail: 'read-only' }))
    await api('/api/comments', { method: 'POST', body: {} }).catch(() => {})
    assert.deepEqual(seen, ['/api/gap?theme_id=1'])
  } finally {
    setUnauthorisedHandler(null)
  }
  // without a handler a 401 is just an ApiError
  mockFetch(reply(401, { detail: 'Not signed in' }))
  assert.equal((await api('/api/x').catch((x) => x)).status, 401)
})
