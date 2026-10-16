// Words and scales behind the Trends bars. Run: npm test (node --test).
import assert from 'node:assert/strict'
import { test } from 'node:test'
import * as d3 from 'd3'
import { LENS_NEED, needLine, reasonText, shortfall, stepPath, usualLine, verdict, weekEnd, weekRange, yScale } from '../src/charts/trendText.js'

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
  assert.equal(shortfall(-0.39, 0.4), 'About as usual')
  // clearly more than usual says so (owner decision), in the same e^gap terms
  assert.equal(shortfall(-0.4, 0.4), 'About 1.5 times more articles than usual')
  assert.equal(shortfall(-0.47, 0.4), 'About 1.6 times more articles than usual')
  assert.equal(shortfall(2.5, 0.4), 'About 12 times fewer articles than usual')
})

test('verdict sentences carry the drawn numbers or the reason', () => {
  assert.equal(verdict(row(), 0.4, need), 'Last 4 weeks: 238 articles against about 248 usual. About as usual.')
  assert.equal(verdict(row({ gap: 0.51, articles_4w: 166, expected_4w: 279.4 }), 0.4, need),
    'Last 4 weeks: 166 articles against about 279 usual. About 1.7 times fewer articles than usual.')
  assert.equal(verdict(row({ in_progress: true, gap: null, insufficient: true }), 0.4, need), 'This week is still coming in. Not judged yet.')
  // economy on the snapshot: 700 against about 401 no longer reads 'as usual'
  assert.equal(verdict(row({ gap: Math.log((401.0 + 5) / (700 + 5)), articles_4w: 700, expected_4w: 401.0 }), 0.4, need),
    'Last 4 weeks: 700 articles against about 401 usual. About 1.7 times more articles than usual.')
  // too few expected is about the usual level, and quotes it
  assert.equal(verdict(row({ gap: null, insufficient: true, reason: 'too_few_expected', articles_4w: 6, expected_4w: 1.8 }), 0.4, need),
    'Last 4 weeks: 6 articles against about 2 usual. The usual level is too low to judge.')
  assert.equal(reasonText('too_few_expected', need, false), 'Usual level too low to judge')
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
