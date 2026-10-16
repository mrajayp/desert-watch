// Words and scales behind the Trends bars. Run: npm test (node --test).
import assert from 'node:assert/strict'
import { test } from 'node:test'
import * as d3 from 'd3'
import { LENS_NEED, needLine, reasonText, shortfall, stepPath, verdict, weekEnd, weekRange, yScale } from '../src/charts/trendText.js'

const need = LENS_NEED.audience
const row = (o) => ({ week: '2026-10-05', articles: 105, articles_all: 148, gap: 0.04, insufficient: false, in_progress: false,
  articles_4w: 238, expected_4w: 248.38, reason: null, ...o })

test('week ranges and ends', () => {
  assert.equal(weekRange('2026-10-05'), '5 to 11 Oct 2026')
  assert.equal(weekRange('2026-09-28'), '28 Sep to 4 Oct 2026')
  assert.equal(weekRange('2025-12-29'), '29 Dec 2025 to 4 Jan 2026')
  assert.equal(weekEnd('2026-10-05'), '2026-10-11')
  assert.equal(weekEnd('2025-12-29'), '2026-01-04')
})

test('pill wording follows red_from and e^gap', () => {
  assert.equal(shortfall(0.64, 0.4), 'About 1.9 times fewer articles than usual')
  assert.equal(shortfall(0.4, 0.4), 'About 1.5 times fewer articles than usual')
  assert.equal(shortfall(0.39, 0.4), 'About as usual')
  assert.equal(shortfall(-0.6, 0.4), 'About as usual')
  assert.equal(shortfall(2.5, 0.4), 'About 12 times fewer articles than usual')
})

test('verdict sentences carry the drawn numbers or the reason', () => {
  assert.equal(verdict(row(), 0.4, need), 'Last 4 weeks: 238 articles against about 248 usual. About as usual.')
  assert.equal(verdict(row({ gap: 0.51, articles_4w: 166, expected_4w: 279.4 }), 0.4, need),
    'Last 4 weeks: 166 articles against about 279 usual. About 1.7 times fewer articles than usual.')
  assert.equal(verdict(row({ in_progress: true, gap: null, insufficient: true }), 0.4, need), 'This week is still coming in. Not judged yet.')
  assert.equal(verdict(row({ gap: null, insufficient: true, reason: 'too_few_expected' }), 0.4, need),
    'Last 4 weeks: not judged. Too few articles expected to judge.')
  assert.equal(verdict(row({ gap: null, insufficient: true, reason: 'no_need_data' }), 0.4, need),
    'Last 4 weeks: not judged. No reader data linked to this theme.')
  assert.equal(reasonText('no_need_data', need, false), 'No reader data')
  assert.equal(reasonText('something_new', need, false), 'Not scored yet')
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

test('usual line breaks where there is no value', () => {
  const rows = ['2026-09-21', '2026-09-28', '2026-10-05', '2026-10-12'].map((week, i) => ({ week, v: [10, 20, null, 5][i] }))
  const x = d3.scaleBand().domain(rows.map((r) => r.week)).range([0, 40])
  const y = d3.scaleLinear().domain([0, 20]).range([20, 0])
  assert.equal(stepPath(rows, x, x.step(), y, (r) => r.v), 'M0.0,10.0H10.0V0.0H20.0M30.0,15.0H40.0')
  assert.equal(stepPath(rows, x, x.step(), y, () => null), '')
})
