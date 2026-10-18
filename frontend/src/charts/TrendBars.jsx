// Articles per week, one small panel per theme (Trends page). Bars = articles that week from the
// comparable outlets (the set the gap score counts), grey step = the usual level for that much need
// (expected_week, see usualLine for the 4 weeks in focus), strip = the verdict for the 4 weeks ending
// that week. Every number in the tooltip is one that is drawn. Payload: /api/cells/trends.
// Keyboard: the plot takes focus, arrow keys move between weeks, Enter lists a week's articles and
// G opens its gap.
import * as d3 from 'd3'
import { memo, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { fmt, gapFill } from './scales'
import { DAY, about, articles, judged, lensNeed, levelLegend, needLine, noSearchData, notJudged, shortfall, stepPath, trendGroups, usualLine, utc, verdict, weekEnd, weekRange, yScale } from './trendText'
import { HatchDefs, themeLabel, useSize, useTooltip } from './util'
import { t, utcFormat } from '../i18n.js'

// focus from the keyboard, not from a click (a click opens the week's articles instead)
const keyFocus = (el) => { try { return el.matches(':focus-visible') } catch { return true } } // i18n-ok: a CSS selector, never shown

// in the interface language, so formatted when drawn (never at import time)
const dayMonth = (d) => utcFormat('%-d %b')(d)

// th: the theme (the prop keeps its name t; inside, t is the translation function)
const Panel = memo(function Panel({ t: th, rows, hasNeed, note, fullName, width, lens, reference, scoredWeek, red, lang, selected, onSelect, onPickWeek, onPickBar }) {
  const wrap = useRef(null)
  const tip = useTooltip()
  const [hover, setHover] = useState(null)
  const [focused, setFocused] = useState(false)
  const need = lensNeed(lens, reference)
  const name = (lang === 'ar' ? th.name_ar : th.name_en) || th.name_en
  // chart text is 11px at the smallest: the axis gutter and the foot leave room for it
  const L = 34, R = 4, T = 16, y0 = 116, sy = y0 + 3, sh = 7, H = sy + sh + 17
  const xs = d3.scaleBand().domain(rows.map((r) => r.week)).range([L, width - R])
  const step = xs.step()
  // no usual level on the week still coming in: its need is not complete either
  const lined = (r) => hasNeed && !r.in_progress && r.expected_week != null
  const done = rows.filter((r) => !r.in_progress)
  // the week the header describes: the latest complete one. On the search lens, when that week has no
  // search data yet (it comes with the weekly import), the lens's latest scored week instead.
  const latest = done[done.length - 1]
  const scored = scoredWeek && latest && scoredWeek < latest.week && noSearchData(latest) ? done.find((r) => r.week === scoredWeek) : null
  const last = scored || latest
  const lastIdx = last ? rows.indexOf(last) : rows.length - 1
  // the window in focus: the hovered week, else the week the header describes
  const focus = hover ?? lastIdx
  const usual = usualLine(rows, focus, hasNeed)
  // the axis allows for every window the reader can focus, so it does not jump on hover
  const usualTop = useMemo(() => d3.max(rows, (_, f) => d3.max(usualLine(rows, f, hasNeed))) || 0, [rows, hasNeed])
  const [y, ticks] = yScale(Math.max(4, d3.max(rows, (r) => r.articles) || 0, usualTop), [y0, T])
  const path = stepPath(rows, xs, step, y, (r, i) => usual[i])
  const cur = rows.find((r) => r.in_progress)
  const a4 = last ? last.articles_4w ?? d3.sum(rows.slice(Math.max(0, lastIdx - 3), lastIdx + 1), (r) => r.articles) : 0
  // month labels at the 1st of each month (quarters only on narrow panels), January shows the year
  const first = utc(rows[0].week)
  const months = d3.utcMonth.range(d3.utcMonth.ceil(first), new Date(utc(rows[rows.length - 1].week).getTime() + 7 * DAY))
    .filter((m) => width >= 420 || m.getUTCMonth() % 3 === 0)
    .map((m) => ({ m, x: L + ((m - first) / (7 * DAY)) * step }))
    .filter((d) => d.x < width - R - 16)
  const at = (e) => {
    const box = e.currentTarget.ownerSVGElement.getBoundingClientRect()
    const px = ((e.clientX - box.left) / box.width) * width
    return Math.max(0, Math.min(rows.length - 1, Math.floor((px - L) / step)))
  }
  const tipFor = (r, keys) => {
    const nl = hasNeed ? needLine(r, need, lens) : null
    return (
      <div>
        <b>{weekRange(r.week)}</b>
        <div>{r.in_progress ? t('{articles} from outlets we followed all year so far', { articles: articles(r.articles) })
          : t('{articles} from outlets we followed all year', { articles: articles(r.articles) })}</div>
        {r.articles_all !== r.articles && <div>{t('{articles} from all sources', { articles: articles(r.articles_all) })}</div>}
        {lined(r) && <div>{t('Expected for this week: {n}', { n: about(r.expected_week) })}</div>}
        {nl && <div>{nl}</div>}
        <div style={{ marginTop: 4 }}>{verdict(r, red, need)}</div>
        {onPickBar && <div className="small muted">{keys ? t('Enter lists this week’s articles. G opens the gap.') : t('Click for this week’s articles')}</div>}
      </div>)
  }
  const show = (e) => {
    const i = at(e)
    setHover(i)
    tip.show(e, tipFor(rows[i]), wrap.current)
  }
  // keyboard: the tooltip sits over the week's bar
  const showKey = (i, plot) => {
    const box = plot.getBoundingClientRect()
    const px = box.left + ((xs(rows[i].week) + step / 2 - L) / (width - R - L)) * box.width
    setHover(i)
    tip.show({ clientX: px, clientY: box.top + box.height / 3 }, tipFor(rows[i], true), wrap.current)
  }
  const onKey = (e) => {
    const cur = hover ?? lastIdx
    const go = { ArrowLeft: cur - 1, ArrowRight: cur + 1, Home: 0, End: rows.length - 1 }[e.key]
    if (go != null) {
      e.preventDefault()
      setFocused(true)
      showKey(Math.max(0, Math.min(rows.length - 1, go)), e.currentTarget)
    } else if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      onPickBar?.(th, rows[cur])
    } else if ((e.key === 'g' || e.key === 'G') && !rows[cur].in_progress) {
      onPickWeek?.(th.id, rows[cur].week)
    }
  }
  const hide = () => { setHover(null); tip.hide() }
  const curX = cur ? xs(cur.week) + step / 2 : null
  return (
    <div ref={wrap} className="card viz trend-panel">
      <div className="trend-head">
        <button type="button" className="linkish" aria-pressed={!!selected} title={t('{name}. Show this theme in the charts below.', { name })}
          onClick={() => onSelect?.(th.id)}>{fullName ? name : themeLabel(th, lang)}</button>
        {last && (judged(last) ? (() => { const short = last.gap >= red; return (
          <button type="button" className={short ? 'pill flag' : 'pill'}
            title={t('{week}. {verdict} Click for the full gap.', { week: weekRange(last.week), verdict: verdict(last, red, need) })}
            onClick={() => onPickWeek?.(th.id, last.week)}>
            {short && <span className="glyph" aria-hidden="true">⚠︎</span>}
            {shortfall(last.gap, red)}</button>) })()
          // a week that could not be judged: the pill explains the term (the strip under the chart still opens the gap)
          : <Link className="pill" to="/help#not-judged" title={t('{week}. {verdict} Why a week is not judged.', { week: weekRange(last.week), verdict: verdict(last, red, need) })}>
            {notJudged(last.reason, need)}</Link>)}
      </div>
      <div className="small muted" style={{ margin: '2px 0 4px' }}>
        {scored ? t('4 weeks to {date}: {articles}.', { date: dayMonth(utc(weekEnd(last.week))), articles: articles(a4) })
          : t('Last 4 weeks: {articles}.', { articles: articles(a4) })}
        {hasNeed && last?.expected_4w != null ? ` ${t('Expected: {n}.', { n: about(last.expected_4w) })}` : ''}{!hasNeed && note ? ` ${note}` : ''}</div>
      <svg viewBox={`0 0 ${width} ${H}`} role="group" aria-label={t('{name}: articles per week', { name })}>
        <HatchDefs id={`tb-hatch-${th.id}`} />
        {hover != null && !rows[hover].in_progress && (
          // the 4 weeks the hovered week's verdict covers
          <rect x={xs(rows[Math.max(0, hover - 3)].week)} y={T} width={step * (hover - Math.max(0, hover - 3) + 1)} height={y0 - T}
            fill="var(--surface-2)" opacity={0.55} />)}
        {hover != null && <rect x={xs(rows[hover].week)} y={T} width={step} height={y0 - T} fill="var(--surface-2)" />}
        {ticks.map((v) => (
          <g key={v}><line x1={L} x2={width - R} y1={y(v)} y2={y(v)} stroke="var(--grid)" />
            <text x={L - 4} y={y(v) + 3} textAnchor="end" className="num" style={{ fontSize: 11 }}>{fmt(v)}</text></g>))}
        <text x={L} y={10} style={{ fontSize: 11, fill: 'var(--muted)' }}>{t('articles a week')}</text>
        {rows.map((r) => {
          const x = xs(r.week) + step * 0.12, w = Math.max(1, step * 0.76), top = y(r.articles)
          if (r.in_progress) {
            return <rect key={r.week} x={x + 0.5} y={top + 0.5} width={Math.max(0.5, w - 1)} height={Math.max(0, y0 - top - 0.5)}
              fill="none" stroke="var(--accent)" strokeWidth={1} strokeDasharray="2 1.5" />
          }
          return r.articles > 0 ? <rect key={r.week} x={x} y={top} width={w} height={y0 - top} fill="var(--accent)" /> : null
        })}
        {hasNeed ? (path && <path d={path} fill="none" stroke="var(--ink-2)" strokeWidth={1.6} strokeLinejoin="round" />)
          : <text x={L + 4} y={T + 10} className="halo" style={{ fontSize: 11, fill: 'var(--muted)' }}>{t(need.none)}</text>}
        {cur && <g>
          <line x1={curX} x2={curX} y1={12} y2={Math.max(12, y(cur.articles) - 2)} stroke="var(--muted)" strokeDasharray="1 2" />
          <text x={width - R} y={10} textAnchor="end" style={{ fontSize: 11, fill: 'var(--muted)' }}>{t('still coming in')}</text></g>}
        <rect x={L} y={T} width={width - R - L} height={y0 - T} fill="transparent" style={{ cursor: onPickBar ? 'pointer' : 'default', outline: 'none' }}
          onMouseMove={show} onMouseLeave={() => !focused && hide()} onClick={(e) => onPickBar?.(th, rows[at(e)])}
          tabIndex={0} role="button" aria-label={t('{name}, articles per week. Arrow keys move between weeks. Enter lists a week’s articles, G opens its gap.', { name })}
          onFocus={(e) => { if (keyFocus(e.currentTarget)) { setFocused(true); showKey(hover ?? lastIdx, e.currentTarget) } }}
          onBlur={() => { if (focused) { setFocused(false); hide() } }}
          onKeyDown={onKey} />
        {focused && <rect x={L} y={T} width={width - R - L} height={y0 - T} fill="none" stroke="var(--focus)" strokeWidth={2} rx={2} pointerEvents="none" />}
        {rows.map((r) => {
          const fill = r.in_progress ? null : judged(r) ? (r.gap >= red ? gapFill(r) : 'var(--gap-0)') : `url(#tb-hatch-${th.id})` // i18n-ok: an SVG fill reference, never shown
          return (
            <rect key={r.week} x={xs(r.week)} y={sy} width={step + 0.3} height={sh} fill={fill || 'transparent'}
              style={{ cursor: fill && onPickWeek ? 'pointer' : 'default' }} onClick={fill ? () => onPickWeek?.(th.id, r.week) : undefined}>
              <title>{fill ? t('{week}. {verdict} Click for the full gap.', { week: weekRange(r.week), verdict: verdict(r, red, need) })
                : `${weekRange(r.week)}. ${verdict(r, red, need)}`}</title></rect>)
        })}
        {months.map(({ m, x }) => (
          <g key={+m}><line x1={x} x2={x} y1={sy + sh} y2={sy + sh + 3} stroke="var(--axis)" />
            <text x={x + 2} y={sy + sh + 14} style={{ fontSize: 11 }}>{m.getUTCMonth() === 0 ? m.getUTCFullYear() : utcFormat('%b')(m)}</text></g>))}
      </svg>
      {tip.node}
    </div>
  )
})

// reference: the lens's meta reference (pooled lenses compare with other topics, the others with the theme's own record). scoredWeek: the
// search lens's latest scored week, which the panels open on while the latest week has no search data.
export default function TrendBars({ themes, data, lens, reference, scoredWeek, lang = 'en', selectedId, onSelect, onPickWeek, onPickBar }) {
  const wrap = useRef(null)
  const W = useSize(wrap, 900)
  const cols = W < 560 ? 1 : W < 900 ? 2 : 3
  const width = Math.max(220, Math.floor((W - 12 * (cols - 1)) / cols) - 22) // card padding + border
  const red = data.red_from ?? 0.4
  const need = lensNeed(lens, reference)
  const groups = trendGroups(themes, data, lens)
  return (
    <div ref={wrap}>
      {groups.map((g) => (
        <div key={g.label}>
          {groups.length > 1 && <div className="trend-group">{t(g.label)}</div>}
          {g.note && <p className="small muted" style={{ margin: '0 0 8px' }}>{t(g.note)}</p>}
          <div className="trend-grid" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}>
            {g.themes.map((t) => (
              <Panel key={t.id} t={t} rows={data.themes[t.id].rows} hasNeed={data.themes[t.id].has_need} note={data.themes[t.id].note} fullName={g.fullNames} width={width}
                lens={lens} reference={reference} scoredWeek={scoredWeek} red={red} lang={lang} selected={t.id === selectedId}
                onSelect={onSelect} onPickWeek={onPickWeek} onPickBar={onPickBar} />))}
          </div>
        </div>))}
      <div className="legend" style={{ marginTop: 12 }}>
        <span><span className="sw" style={{ background: 'var(--accent)' }} />{t('Articles from the outlets we followed all year')}</span>
        <span><span className="sw" style={{ background: 'var(--ink-2)', height: 2, verticalAlign: 3 }} />{levelLegend(need)}</span>
        <span><span className="ramp" style={{ marginInlineEnd: 5 }}>{[2, 3, 4, 5, 6].map((i) => <span key={i} style={{ background: `var(--gap-${i})` }} />)}</span>{t('Last 4 weeks fell clearly short')}</span>
        <span><span className="sw" style={{ background: 'var(--gap-0)', boxShadow: 'inset 0 0 0 1px var(--line)' }} />{t('About as expected, or more')}</span>
        <span><svg width="14" height="12" style={{ verticalAlign: -2, marginInlineEnd: 5 }}><HatchDefs id="tb-hatch-legend" /><rect width="14" height="12" rx="2" fill="url(#tb-hatch-legend)" /></svg>{t('Not judged')}</span>
        <span><span className="sw" style={{ border: '1px dashed var(--accent)', background: 'none' }} />{t('This week, still coming in')}</span>
      </div>
    </div>
  )
}
