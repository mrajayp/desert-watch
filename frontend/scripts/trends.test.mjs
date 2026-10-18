// Words and scales behind the Trends bars. Run: npm test (node --test).
import assert from 'node:assert/strict'
import { test } from 'node:test'
import * as d3 from 'd3'
import { LENS_NEED, SEARCH_FEW, lensNeed, trendGroups, levelLegend, needLine, noSearchData, notJudged, reasonText, shortfall, stepPath, usualLine, verdict, weekEnd, weekRange, yScale } from '../src/charts/trendText.js'
import { GAP_BINS, GAP_STEPS, RED_FROM, gapBins, gapFill, gapLabel } from '../src/charts/scales.js'

const need = LENS_NEED.audience

test('one red threshold: colour and label start at red_from on every page', () => {
  // the fallback mirrors settings.GAP_RED_FROM; pages pass meta.red_from
  assert.equal(RED_FROM, 0.4)
  assert.equal(GAP_BINS[0], RED_FROM)
  assert.deepEqual(gapBins(0.3), [0.3, 0.7, 1.0, 1.5, 2.2])
  assert.equal(GAP_STEPS.length, gapBins().length)
  // below red: neutral and "About as expected", so the old 0.15 band is no longer tinted
  assert.equal(gapFill({ gap: 0.2 }), 'var(--gap-0)')
  assert.equal(gapFill({ gap: 0.39 }, 0.4), 'var(--gap-0)')
  assert.equal(gapLabel(0.39, 0.4), 'About as expected')
  assert.equal(gapLabel(-0.5), 'About as expected')
  // from red: the first red step and a multiple, in the same words as the Trends pill
  assert.equal(gapFill({ gap: 0.4 }, 0.4), 'var(--gap-2)')
  assert.equal(gapLabel(0.4, 0.4), 'About 1.5 times fewer articles than expected')
  assert.equal(shortfall(0.4, 0.4), 'About 1.5 times fewer articles than expected')
  // the threshold is the argument, not a constant
  assert.equal(gapFill({ gap: 0.4 }, 0.5), 'var(--gap-0)')
  assert.equal(gapLabel(0.4, 0.5), 'About as expected')
  assert.equal(gapFill({ gap: 0.3 }, 0.25), 'var(--gap-2)')
  // the steps above red keep their colours
  assert.equal(gapFill({ gap: 0.7 }), 'var(--gap-3)')
  assert.equal(gapFill({ gap: 1.0 }), 'var(--gap-4)')
  assert.equal(gapFill({ gap: 1.5 }), 'var(--gap-5)')
  assert.equal(gapFill({ gap: 2.2 }), 'var(--gap-6)')
  assert.equal(gapLabel(2.5), 'About 12 times fewer articles than expected')
  // not judged: one term on every page
  assert.equal(gapFill({ gap: 0.9, insufficient: true }), null)
  assert.equal(gapFill({ gap: null }), null)
  assert.equal(gapFill(null), null)
  assert.equal(gapLabel(null), 'Not judged')
})
const row = (o) => ({ week: '2026-10-05', articles: 105, articles_all: 148, gap: 0.04, insufficient: false, in_progress: false,
  articles_4w: 238, expected_4w: 248.38, reason: null, ...o })

test('week ranges and ends', () => {
  assert.equal(weekRange('2026-10-05'), '5 to 11 Oct 2026')
  assert.equal(weekRange('2026-09-28'), '28 Sep to 4 Oct 2026')
  assert.equal(weekRange('2025-12-29'), '29 Dec 2025 to 4 Jan 2026')
  assert.equal(weekEnd('2026-10-05'), '2026-10-11')
  assert.equal(weekEnd('2025-12-29'), '2026-01-04')
})

test('pill wording follows red_from and e^gap, and says expected on every lens', () => {
  assert.equal(shortfall(0.64, 0.4), 'About 1.9 times fewer articles than expected')
  assert.equal(shortfall(0.4, 0.4), 'About 1.5 times fewer articles than expected')
  assert.equal(shortfall(0.39, 0.4), 'About as expected')
  assert.equal(shortfall(-0.39, 0.4), 'About as expected')
  // clearly more than expected says so (owner decision), in the same e^gap terms
  assert.equal(shortfall(-0.4, 0.4), 'About 1.5 times more articles than expected')
  assert.equal(shortfall(-0.47, 0.4), 'About 1.6 times more articles than expected')
  assert.equal(shortfall(2.5, 0.4), 'About 12 times fewer articles than expected')
})

test('verdict sentences carry the drawn numbers or the reason', () => {
  // an own-record lens names its comparison: this theme's usual level
  assert.equal(verdict(row(), 0.4, need), 'Last 4 weeks: 238 articles against about 248 expected from this theme’s usual level. About as expected.')
  assert.equal(verdict(row({ gap: 0.51, articles_4w: 166, expected_4w: 279.4 }), 0.4, need),
    'Last 4 weeks: 166 articles against about 279 expected from this theme’s usual level. About 1.7 times fewer articles than expected.')
  assert.equal(verdict(row({ in_progress: true, gap: null, insufficient: true }), 0.4, need), 'This week is still coming in. Not judged yet.')
  // economy on the snapshot: 700 against about 401 no longer reads 'as expected'
  assert.equal(verdict(row({ gap: Math.log((401.0 + 5) / (700 + 5)), articles_4w: 700, expected_4w: 401.0 }), 0.4, need),
    'Last 4 weeks: 700 articles against about 401 expected from this theme’s usual level. About 1.7 times more articles than expected.')
  // too few expected is about the expected level, and quotes it
  assert.equal(verdict(row({ gap: null, insufficient: true, reason: 'too_few_expected', articles_4w: 6, expected_4w: 1.8 }), 0.4, need),
    'Last 4 weeks: 6 articles against about 1.8 expected from this theme’s usual level. The expected level is too low to judge.')
  assert.equal(reasonText('too_few_expected', need, false), 'expected level too low')
  assert.equal(verdict(row({ gap: null, insufficient: true, reason: 'no_need_data' }), 0.4, need),
    'Last 4 weeks: not judged. No reader data linked to this theme.')
  assert.equal(reasonText('no_need_data', need, false), 'no reader data')
  // one term, "Not judged", then the reason; a reason this file does not know adds nothing
  assert.equal(notJudged('too_few_expected', need), 'Not judged · expected level too low')
  assert.equal(notJudged('no_need_data', need), 'Not judged · no reader data')
  assert.equal(reasonText('something_new', need, false), '')
  assert.equal(notJudged('something_new', need), 'Not judged')
  assert.equal(verdict(row({ gap: null, insufficient: true, reason: 'something_new' }), 0.4, need), 'Last 4 weeks: not judged.')
})

test('need line shows the lens unit, the language split and trimmed spikes', () => {
  assert.equal(needLine({ need_week: 1880, need_week_raw: 1880, need_en: 1637, need_ar: 243 }, need, 'audience'),
    'Wikipedia views: 1,880 (English 1,637, Arabic 243).')
  assert.equal(needLine({ need_week: 1100, need_week_raw: 3600, need_en: 1000, need_ar: 100 }, need, 'audience'),
    'Wikipedia views: 1,100 (English 1,000, Arabic 100). Before we trimmed one-day spikes: 3,600.')
  assert.equal(needLine({ need_week: 3, need_week_raw: 3, need_en: null }, LENS_NEED.humanitarian, 'humanitarian'), 'ReliefWeb reports: 3.')
  assert.equal(needLine({ need_week: null }, need, 'audience'), null)
})

test('y axis starts at 0 with 3 or 4 labelled gridlines ending on the top', () => {
  for (const top of [4, 7, 12, 74, 107, 184, 235, 525, 1810]) {
    const [y, ticks] = yScale(top, [100, 0])
    assert.equal(y.domain()[0], 0)
    assert.ok(y.domain()[1] >= top, `top ${top}`)
    assert.ok(ticks.length >= 3 && ticks.length <= 4, `top ${top}: ${ticks}`)
    assert.equal(ticks[0], 0)
    assert.equal(ticks[ticks.length - 1], y.domain()[1])
  }
  assert.deepEqual(yScale(4, [100, 0])[1], [0, 2, 4])
})

test('the 4 weeks in focus add up to the usual level the verdict quotes', () => {
  // each week's own baseline drifts: 0.02, 0.025, 0.03, 0.035 articles per view
  const rows = [400, 500, 600, 800, 700, 300].map((need_week, i) => {
    const ref = 0.02 + 0.005 * Math.min(i, 3)
    return { week: `w${i}`, need_week, ref, expected_week: need_week * ref, in_progress: i === 5 }
  })
  rows.forEach((r, i) => { if (i >= 3) r.expected_4w = r.ref * (rows[i - 3].need_week + rows[i - 2].need_week + rows[i - 1].need_week + r.need_week) })
  const sum4 = (vals, f) => vals.slice(f - 3, f + 1).reduce((a, b) => a + b, 0)
  for (const f of [3, 4]) {
    const vals = usualLine(rows, f, true)
    assert.ok(Math.abs(sum4(vals, f) - rows[f].expected_4w) < 1e-9, `focus ${f}`)
    assert.equal(vals[f], rows[f].expected_week)          // the focus week's own step is unchanged
  }
  const own = rows.map((r) => r.expected_week)
  assert.ok(Math.abs(sum4(own, 3) - rows[3].expected_4w) > 1)   // own baselines would not add up
  const vals = usualLine(rows, 3, true)
  assert.equal(vals[5], null)                               // nothing on the week still coming in
  assert.equal(vals[4], rows[4].expected_week)              // outside the window: its own baseline
  assert.deepEqual(usualLine(rows, 3, false), rows.map(() => null))
  // focus on the week still coming in: every week keeps its own baseline
  assert.deepEqual(usualLine(rows, 5, true), [...own.slice(0, 5), null])
})

test('usual line breaks where there is no value', () => {
  const rows = ['2026-09-21', '2026-09-28', '2026-10-05', '2026-10-12'].map((week, i) => ({ week, v: [10, 20, null, 5][i] }))
  const x = d3.scaleBand().domain(rows.map((r) => r.week)).range([0, 40])
  const y = d3.scaleLinear().domain([0, 20]).range([20, 0])
  assert.equal(stepPath(rows, x, x.step(), y, (r) => r.v), 'M0.0,10.0H10.0V0.0H20.0M30.0,15.0H40.0')
  assert.equal(stepPath(rows, x, x.step(), y, () => null), '')
})

test('search lens speaks of Google searches, never Wikipedia', () => {
  const search = lensNeed('search', 'own_history')
  assert.equal(search, LENS_NEED.search)
  assert.equal(needLine({ need_week: 182, need_week_raw: 182, need_en: null }, search, 'search'), 'Google searches (index): 182.')
  assert.equal(reasonText('no_need_data', search, true), 'Too few searches in Libya to compare')
  assert.equal(reasonText('no_need_data', search, false), 'too few searches to compare')
  assert.equal(notJudged('no_need_data', search), 'Not judged · too few searches to compare')
  // "usual level" survives in the legend alone (it names the own-record comparison)
  assert.equal(levelLegend(search), 'Usual level for this much search interest')
  // a week that has ended but is not imported yet, or one Google held back
  const gone = row({ gap: null, insufficient: true, reason: 'no_search_data', need_week: 0, expected_week: null, ref: null, expected_4w: null })
  assert.equal(verdict(gone, 0.4, search), 'Last 4 weeks: not judged. Google gave no search data for one of these 4 weeks.')
  assert.equal(reasonText('no_search_data', search, false), 'no search data for a week')
  assert.ok(noSearchData(gone) && noSearchData({ need_week: 40, reason: 'no_search_data' }) && !noSearchData({ need_week: 40, reason: null }))
  for (const text of [needLine(gone, search, 'search'), verdict(gone, 0.4, search), reasonText('no_need_data', search, true)]) {
    assert.ok(!/Wikipedia|reader/.test(text ?? ''), text)
  }
})

test('the usual line breaks on a week with no search data instead of dropping to 0', () => {
  const rows = [
    { week: 'w0', need_week: 100, ref: 2, expected_week: 200 },
    { week: 'w1', need_week: 110, ref: 2, expected_week: 220 },
    { week: 'w2', need_week: 90, ref: 2, expected_week: 180 },
    { week: 'w3', need_week: 100, ref: 2.1, expected_week: 210, expected_4w: 2.1 * 400 },
    { week: 'w4', need_week: 0, ref: null, expected_week: null, expected_4w: null, reason: 'no_search_data' },
    { week: 'w5', need_week: 0, expected_week: null, in_progress: true },
  ]
  assert.deepEqual(usualLine(rows, 4, true), [200, 220, 180, 210, null, null])
  // open on the latest scored week: its 4 weeks at its baseline, the missing week still empty
  assert.deepEqual(usualLine(rows, 3, true), [210, 231, 189, 210, null, null])
})

test('pooled lenses say expected from other topics; own-record lenses from this theme’s usual level', () => {
  const hum = lensNeed('humanitarian', 'pooled')
  assert.ok(hum.pooled && !lensNeed('humanitarian').pooled && !LENS_NEED.humanitarian.pooled)
  assert.equal(verdict(row(), 0.4, hum), 'Last 4 weeks: 238 articles against about 248 expected from other topics. About as expected.')
  assert.equal(verdict(row({ gap: 0.51, articles_4w: 166, expected_4w: 279.4 }), 0.4, hum),
    'Last 4 weeks: 166 articles against about 279 expected from other topics. About 1.7 times fewer articles than expected.')
  assert.equal(shortfall(-0.47, 0.4, hum), 'About 1.6 times more articles than expected')
  assert.equal(verdict(row({ gap: null, insufficient: true, reason: 'too_few_expected', articles_4w: 6, expected_4w: 1.8 }), 0.4, hum),
    'Last 4 weeks: 6 articles against about 1.8 expected from other topics. The expected level is too low to judge.')
  assert.equal(reasonText('too_few_expected', hum, false), 'expected level too low')
  assert.equal(levelLegend(hum), 'Expected level for this many ReliefWeb reports, going by other topics')
  // one report is below the humanitarian need floor
  assert.equal(reasonText('too_little_need', hum, false), 'too few reports')
  assert.equal(notJudged('too_little_need', hum), 'Not judged · too few reports')
  assert.equal(verdict(row({ gap: null, insufficient: true, reason: 'too_little_need' }), 0.4, hum),
    'Last 4 weeks: not judged. There were too few ReliefWeb reports to judge.')
  assert.equal(reasonText('too_little_need', LENS_NEED.audience, false), 'too little data')
  // own-record lenses name their comparison but still say expected
  assert.equal(verdict(row(), 0.4, lensNeed('audience', 'own_history')), 'Last 4 weeks: 238 articles against about 248 expected from this theme’s usual level. About as expected.')
})

test('search lens: measured themes first, the rest keep their charts under a heading that says why', () => {
  const themes = [{ id: 1, group: null }, { id: 2, group: null }, { id: 3, group: 'gender' }, { id: 4, group: null }]
  const data = { themes: { 1: { has_need: false, rows: [1] }, 2: { has_need: true, rows: [1] }, 3: { has_need: false, rows: [1] }, 4: { has_need: true, rows: [1] } } }
  const g = trendGroups(themes, data, 'search')
  assert.deepEqual(g.map((x) => [x.label, x.themes.map((t) => t.id)]), [['Enough searches to compare', [2, 4]], ['Too few searches to compare', [1, 3]]])
  assert.equal(g[1].note, SEARCH_FEW)
  assert.ok(g.every((x) => x.fullNames))
  assert.equal(reasonText('no_need_data', lensNeed('search'), false), 'too few searches to compare')
  // other lenses keep General then Gender
  assert.deepEqual(trendGroups(themes, data, 'audience').map((x) => x.label), ['General', 'Gender'])
})
