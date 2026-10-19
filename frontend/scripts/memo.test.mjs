// The API client's 10-minute GET memo for /api/cells and /api/network (api.js), with a mocked fetch.
// Run: npm test (node --test).
//   the same URL twice -> one fetch; a different language or a different URL -> its own fetch
//   past 10 minutes, after invalidateMemo() (what refresh() calls) or with fresh: true -> a new fetch
//   a failure is never kept; an aborted caller is rejected but the shared answer is still kept
//   other paths and POSTs are never memoised
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { MEMO_MS, _setClock, api, invalidateMemo, isMemoable, memoSize } from '../src/api.js'
import { setLang } from '../src/i18n.js'

let calls = []
let answer = () => ({ ok: true, status: 200, json: async () => ({ n: calls.length }) })
globalThis.fetch = async (path, init) => { calls.push({ path, init }); return answer(path, init) }
const reset = () => { calls = []; invalidateMemo(); _setClock(null); setLang('en') }

test('which paths are memoised', () => {
  assert.ok(isMemoable('/api/cells?lens=audience&week=2026-10-05'))
  assert.ok(isMemoable('/api/network'))
  assert.ok(!isMemoable('/api/cells/trends?lens=audience')) // the Trends payload is its own, uncached call
  assert.ok(!isMemoable('/api/gap?theme_id=1'))
  assert.ok(!isMemoable('/api/network', 'POST'))
})

test('the same URL is fetched once within 10 minutes, and again after', async () => {
  reset()
  let now = 1_000_000
  _setClock(() => now)
  const a = await api('/api/cells?lens=audience&week=2026-10-05')
  const b = await api('/api/cells?lens=audience&week=2026-10-05')
  assert.deepEqual(a, b)
  assert.equal(calls.length, 1)
  assert.equal(memoSize(), 1)
  await api('/api/cells?lens=audience&week=2026-09-28')
  assert.equal(calls.length, 2)
  now += MEMO_MS - 1
  await api('/api/cells?lens=audience&week=2026-10-05')
  assert.equal(calls.length, 2)
  now += 2
  await api('/api/cells?lens=audience&week=2026-10-05')
  assert.equal(calls.length, 3)
})

test('refresh (invalidateMemo) and fresh: true go to the server', async () => {
  reset()
  await api('/api/network?kinds=outlet_region&min_weight=2')
  await api('/api/network?kinds=outlet_region&min_weight=2')
  assert.equal(calls.length, 1)
  invalidateMemo()
  await api('/api/network?kinds=outlet_region&min_weight=2')
  assert.equal(calls.length, 2)
  await api('/api/network?kinds=outlet_region&min_weight=2', { fresh: true })
  assert.equal(calls.length, 3)
  await api('/api/network?kinds=outlet_region&min_weight=2')
  assert.equal(calls.length, 3) // the fresh answer refilled the memo
})

test('the interface language is part of the key', async () => {
  reset()
  await api('/api/cells?week=2026-10-05')
  setLang('ar')
  await api('/api/cells?week=2026-10-05')
  assert.equal(calls.length, 2)
  assert.equal(calls[1].init.headers['X-Lang'], 'ar')
  setLang('en')
})

test('a failed answer is not kept', async () => {
  reset()
  answer = () => ({ ok: false, status: 500, statusText: 'boom', json: async () => { throw new Error('not json') } })
  await assert.rejects(api('/api/cells?week=w'))
  assert.equal(memoSize(), 0)
  answer = () => ({ ok: true, status: 200, json: async () => ({ ok: 1 }) })
  assert.deepEqual(await api('/api/cells?week=w'), { ok: 1 })
  assert.equal(calls.length, 2)
})

test('an aborted caller gets an AbortError while the shared answer is still kept for the next one', async () => {
  reset()
  let release
  answer = () => new Promise((resolve) => { release = () => resolve({ ok: true, status: 200, json: async () => ({ late: true }) }) })
  const ac = new AbortController()
  const p = api('/api/cells?week=x', { signal: ac.signal })
  ac.abort()
  const e = await p.catch((x) => x)
  assert.equal(e.name, 'AbortError')
  release()
  // the second caller shares the same fetch (no new call) and gets its answer
  assert.deepEqual(await api('/api/cells?week=x'), { late: true })
  assert.equal(calls.length, 1)
})

test('in-flight calls for one URL are shared', async () => {
  reset()
  let release
  answer = () => new Promise((resolve) => { release = () => resolve({ ok: true, status: 200, json: async () => ({ shared: true }) }) })
  const p1 = api('/api/network?week=w'), p2 = api('/api/network?week=w')
  release()
  assert.deepEqual(await Promise.all([p1, p2]), [{ shared: true }, { shared: true }])
  assert.equal(calls.length, 1)
})

test('other GETs are never memoised', async () => {
  reset()
  answer = () => ({ ok: true, status: 200, json: async () => ({}) })
  await api('/api/gap?theme_id=1&region_id=2')
  await api('/api/gap?theme_id=1&region_id=2')
  assert.equal(calls.length, 2)
  assert.equal(memoSize(), 0)
})
