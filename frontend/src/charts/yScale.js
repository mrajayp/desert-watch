// The y axis of the Trends bars: linear from 0 with 3-4 labelled gridlines (0 included) ending on the top
// of the domain. Its own module because it is the only thing in the wording file (trendText.js, which the
// landing page uses) that needs d3-scale, and the landing page's chunk should carry no d3 but the date
// formatter. Checked by scripts/trends.test.mjs.
import { nice, ticks } from 'd3-array'
import { scaleLinear } from 'd3-scale'

export function yScale(top, range) {
  for (const n of [3, 2, 4]) {
    const hi = nice(0, top, n)[1]
    const tk = ticks(0, hi, n)
    if (tk.length >= 3 && tk.length <= 4 && tk[tk.length - 1] === hi) return [scaleLinear().domain([0, hi]).range(range), tk]
  }
  const y = scaleLinear().domain([0, top]).nice(3).range(range)
  return [y, y.ticks(3)]
}
