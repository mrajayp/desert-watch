// The URL scheme (src/routes.js): builders, parsers and the page filters. Run: npm test (node --test).
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { addPath, applyFilters, articlePath, articlesPath, articlesQuery, detailKind, filterSearch, gapParams, gapPath, idList, loginPath, outletPath, parentPath, parseId, readFilters, safeNext } from '../src/routes.js'

const meta = {
  lenses: [{ key: 'audience', available: true }, { key: 'events', available: false }, { key: 'search', available: true, latest_scored_week: '2026-09-28' }],
  weeks: ['2026-09-21', '2026-09-28', '2026-10-05'], latest_week: '2026-10-05',
  themes: [{ id: 1, group: null }, { id: 2, group: 'gender' }],
}
const sp = (s) => new URLSearchParams(s)

test('detail routes are told apart and know their parent list', () => {
  assert.equal(detailKind('/gaps/3/7'), 'gap')
  assert.equal(detailKind('/articles/12'), 'article')
  assert.equal(detailKind('/outlets/5/'), 'outlet')
  assert.equal(detailKind('/add'), 'add')
  assert.equal(detailKind('/articles'), null)
  assert.equal(detailKind('/gaps/x/7'), null)
  assert.equal(detailKind('/trends'), null)
  assert.equal(parentPath('/gaps/3/7'), '/')
  assert.equal(parentPath('/articles/12'), '/articles')
  assert.equal(parentPath('/outlets/5'), '/outlets')
  assert.equal(parentPath('/add'), '/')
  assert.equal(parentPath('/nowhere'), '/')
})

test('builders leave out empty values and encode the rest', () => {
  assert.equal(gapPath(3, 7), '/gaps/3/7')
  assert.equal(gapPath(3, 7, { lens: 'search', week: '2026-10-05' }), '/gaps/3/7?lens=search&week=2026-10-05')
  assert.equal(gapPath(3, 7, { lens: null, week: undefined }), '/gaps/3/7')
  assert.equal(articlePath(12), '/articles/12')
  assert.equal(outletPath(5), '/outlets/5')
  assert.equal(addPath(), '/add')
  assert.equal(addPath({ theme_ids: [1, 2], region_ids: [] }), '/add?theme=1%2C2')
  assert.equal(addPath({ theme_ids: [1], region_ids: [7] }), '/add?theme=1&region=7')
  assert.equal(loginPath('/gaps/3/7?lens=search'), '/login?next=%2Fgaps%2F3%2F7%3Flens%3Dsearch')
  assert.equal(loginPath('/'), '/login')
  assert.equal(loginPath(''), '/login')
  assert.deepEqual(idList('1,2,x,,4'), [1, 2, 4])
  assert.equal(parseId('12'), 12)
  assert.equal(parseId('12a'), null)
  assert.equal(parseId(undefined), null)
})

test('gap parameters are checked against the app: an unknown lens or a malformed week is dropped', () => {
  assert.deepEqual(gapParams(sp('lens=search&week=2026-10-05'), meta), { lens: 'search', week: '2026-10-05' })
  assert.deepEqual(gapParams(sp('lens=evil&week=yesterday'), meta), { lens: null, week: null })
  assert.deepEqual(gapParams(sp(''), meta), { lens: null, week: null })
})

test('the article list: an /api/items query becomes a URL and comes back', () => {
  const q = { theme_id: 2, region_id: 7, start: '2026-09-14', end: '2026-10-11', basis: 'trend' }
  const path = articlesPath(q)
  assert.equal(path, '/articles?theme=2&region=7&start=2026-09-14&end=2026-10-11&basis=trend')
  const back = articlesQuery(sp(path.slice(path.indexOf('?'))))
  assert.equal(back.theme_id, 2)
  assert.equal(back.region_id, 7)
  assert.equal(back.start, '2026-09-14')
  assert.equal(back.end, '2026-10-11')
  assert.equal(back.basis, 'trend')
  assert.equal(back.days, '') // a date range wins over days, as the API does
  // URL words are accepted too
  assert.equal(articlesPath({ theme: 1, days: 28, lang: 'ar', q: 'سبها' }), '/articles?theme=1&days=28&lang=ar&q=%D8%B3%D8%A8%D9%87%D8%A7')
})

test('the article list: defaults and bad values fall back quietly', () => {
  const d = articlesQuery(sp(''))
  assert.deepEqual(d, { theme_id: '', region_id: '', days: 7, start: '', end: '', lang: '', source: '', q: '', basis: '' })
  const bad = articlesQuery(sp('theme=abc&region=-1&days=lots&start=2026-13-99x&lang=fr&basis=evil&q=' + 'x'.repeat(300)))
  assert.equal(bad.theme_id, '')
  assert.equal(bad.region_id, '')
  assert.equal(bad.days, 7)
  assert.equal(bad.start, '')
  assert.equal(bad.lang, '')
  assert.equal(bad.basis, '')
  assert.equal(bad.q.length, 200)
  assert.equal(articlesQuery(sp('days=99999')).days, 3650)
  assert.equal(articlesQuery(sp('start=2026-10-01')).days, '')
})

test('safeNext only ever returns a path inside this site', () => {
  assert.equal(safeNext('/gaps/3/7?lens=search'), '/gaps/3/7?lens=search')
  assert.equal(safeNext('https://evil.example/'), '/')
  assert.equal(safeNext('//evil.example/'), '/')
  assert.equal(safeNext('/\\evil.example'), '/')
  assert.equal(safeNext('/login?next=/x'), '/')
  assert.equal(safeNext(''), '/')
  assert.equal(safeNext(null), '/')
  assert.equal(safeNext(42), '/')
})

test('page filters: the URL wins, the saved preference is only a default, and both are checked', () => {
  const colours = ['scope', 'alignment']
  // nothing in the URL: the saved lens and colour, the lens's own week
  assert.deepEqual(readFilters(sp(''), meta, { lens: 'search', colorBy: 'alignment' }, colours),
    { lens: 'search', week: '2026-09-28', themeId: '', colorBy: 'alignment' })
  // the URL names everything
  assert.deepEqual(readFilters(sp('lens=audience&week=2026-09-21&theme=group:gender&colour=scope'), meta, { lens: 'search', colorBy: 'alignment' }, colours),
    { lens: 'audience', week: '2026-09-21', themeId: 'group:gender', colorBy: 'scope' })
  // an unavailable or unknown lens, an unknown week, theme or colour fall back
  assert.deepEqual(readFilters(sp('lens=events&week=2026-01-01&theme=99&colour=mood'), meta, { lens: 'nope', colorBy: 'nope' }, colours),
    { lens: 'audience', week: '2026-10-05', themeId: '', colorBy: 'scope' })
  assert.equal(readFilters(sp('theme=2'), meta, {}, colours).themeId, '2')
  assert.equal(readFilters(sp('theme=group:nope'), meta, {}, colours).themeId, '')
})

test('applyFilters writes a patch into the query string and an empty value removes the parameter', () => {
  const next = applyFilters(sp('lens=search&week=2026-09-28&theme=2'), { lens: 'audience', themeId: '', colorBy: 'alignment' })
  assert.equal(next.toString(), 'lens=audience&week=2026-09-28&colour=alignment')
  assert.equal(applyFilters(sp('week=2026-09-28'), { week: null, other: 'ignored' }).toString(), '')
})

test('filterSearch keeps only the filter parameters, to carry from one page to the next', () => {
  assert.equal(filterSearch(sp('lens=search&week=2026-09-28&q=oil&theme=2')), '?lens=search&week=2026-09-28&theme=2')
  assert.equal(filterSearch(sp('q=oil')), '')
})
