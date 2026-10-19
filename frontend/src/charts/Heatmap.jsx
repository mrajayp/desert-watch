// Theme × region grid. Fill = the verdict (red only when the shortfall is larger than chance would
// explain, intensity by the gap from meta.red_from; a pale tint for possibly fewer, blue for more);
// striped = not judged. Each cell also prints the count the score used (articles, from the outlets
// followed all year) so the score is never a black box; the tooltip adds the all-source count when it
// differs and the verdict sentence with its interval and chance.
import { useRef, useState } from 'react'
import { GAP_STEPS, fmt, gapFill, verdictOf } from './scales'
import { gapLabel, verdictSentence } from './trendText'
import { HatchDefs, fitLabel, groupedRows, themeLabel, useSize, useTooltip } from './util'
import { WarningPills } from '../components/Warnings'
import { pick, t } from '../i18n'

// vote codes from the API (real / covered / not_newsworthy)
const voteText = (k, v) => (k === 'real' ? t('{n} real', { n: v }) : k === 'covered' ? t('{n} covered', { n: v })
  : k === 'not_newsworthy' ? t('{n} not newsworthy', { n: v }) : `${v} ${k.replace('_', ' ')}`)

// red: meta.red_from (gapFill falls back to its default until it is known); need: the lens's words
// (trendText.lensNeed), for the verdict sentence
export default function Heatmap({ themes, regions, cells, onSelect, svgRef, unit = 'need', lang = 'en', feedback = {}, red, need }) {
  const wrap = useRef(null)
  const W = useSize(wrap, 700)
  const tip = useTooltip()
  const left = Math.min(240, Math.max(120, W * 0.3))
  const top = 34
  const cw = Math.max(44, (W - left) / Math.max(regions.length, 1))
  const ch = 40
  const hh = 26 // group heading row
  const rows = groupedRows(themes)
  const ys = []
  let yy = top
  rows.forEach((r) => { ys.push(yy); yy += r.header ? hh : ch })
  const H = yy + 4
  const byKey = new Map(cells.map((c) => [`${c.theme_id}:${c.region_id}`, c]))
  const nm = (o) => pick(o)
  // the same grid as a table: the count and the verdict words in each cell, every cell reachable by keyboard
  const [asTable, setAsTable] = useState(false)
  const count = (c) => c?.articles ?? c?.coverage
  return (
    <div ref={wrap} className="viz" onMouseLeave={tip.hide}>
      <div className="row" style={{ justifyContent: 'flex-end', marginBottom: 6 }}>
        <button type="button" className="btn small" aria-pressed={asTable} onClick={() => setAsTable(!asTable)}>{asTable ? t('Show as chart') : t('Show as table')}</button>
      </div>
      {asTable && (
        <div className="scroll">
          <table className="data heat-table">
            <caption className="sr-only">{t('Gap by theme and region')}</caption>
            <thead><tr><th>{t('Theme')}</th>{regions.map((r) => <th key={r.id}>{nm(r)}</th>)}</tr></thead>
            <tbody>{rows.map((row) => row.header ? (
              <tr key={`h-${row.header}`}><th colSpan={regions.length + 1} className="small muted" style={{ textAlign: 'start' }}>{t(row.header)}</th></tr>
            ) : (
              <tr key={row.theme.id}><th scope="row" style={{ textAlign: 'start' }}>{nm(row.theme)}</th>
                {regions.map((r) => {
                  const c = byKey.get(`${row.theme.id}:${r.id}`)
                  return <td key={r.id}>{c ? (
                    <button type="button" className="textbtn" onClick={() => onSelect?.(row.theme.id, r.id)} title={verdictSentence(c, need, red)}>
                      <span className="num">{fmt(count(c))}</span> · {gapLabel(c, red, need)}</button>) : <span className="muted">–</span>}</td>
                })}</tr>))}</tbody>
          </table>
        </div>)}
      <div hidden={asTable}>
      <svg ref={svgRef} viewBox={`0 0 ${Math.max(W, left + cw * regions.length)} ${H}`} role="img" aria-label={t('Gap by theme and region')}>
        <HatchDefs id="hm-hatch" />
        {regions.map((r, j) => (
          <text key={r.id} x={left + j * cw + cw / 2} y={top - 10} textAnchor="middle" style={{ fontSize: 11, fontWeight: 600 }}>
            {nm(r).length > 14 ? nm(r).slice(0, 13) + '…' : nm(r)}</text>))}
        {rows.map((row, i) => row.header ? (
          <g key={`h-${row.header}`} transform={`translate(0,${ys[i]})`}>
            <text x={4} y={hh - 8} style={{ fontSize: 11, fontWeight: 700, fill: 'var(--ink-2)', letterSpacing: '.04em' }}>{t(row.header).toUpperCase()}</text>
            <line x1={4} x2={Math.max(W, left + cw * regions.length)} y1={hh - 2} y2={hh - 2} stroke="var(--grid)" />
          </g>
        ) : (() => { const th = row.theme; return (
          <g key={th.id} transform={`translate(0,${ys[i]})`}>
            <text x={left - 10} y={ch / 2 + 4} textAnchor="end" style={{ fontSize: 12, fill: 'var(--ink)' }}>
              <title>{nm(th)}</title>{fitLabel(themeLabel(th, lang), left - 16)}</text>
            {regions.map((r, j) => {
              const c = byKey.get(`${th.id}:${r.id}`)
              const fill = gapFill(c, red) || (c ? 'url(#hm-hatch)' : 'var(--surface-2)') // i18n-ok: SVG pattern reference, not shown
              const fb = feedback[`${th.id}:${r.id}`]
              const dark = c && verdictOf(c, red) === 'short' && c.gap >= 1.0
              // articles = the count the score used; articles_all = every source (coverage until the API sends them)
              const n = c?.articles ?? c?.coverage
              const all = c?.articles_all ?? c?.coverage
              return (
                <g key={r.id} transform={`translate(${left + j * cw},0)`} style={{ cursor: c ? 'pointer' : 'default' }}
                  onClick={() => c && onSelect?.(th.id, r.id)}
                  onMouseMove={(e) => tip.show(e, c ? (
                    <div><b>{nm(th)} · {nm(r)}</b>
                      <div>{t('{articles} articles · {need} {unit}', { articles: fmt(n), need: fmt(c.need), unit: t(unit) })}</div>
                      {all != null && all !== n && <div className="muted">{t('{n} from all sources', { n: fmt(all) })}</div>}
                      <div>{verdictSentence(c, need, red)}</div>
                      <WarningPills codes={c.flags} block />
                      {fb && <div className="small muted" style={{ marginTop: 4 }}>{t('Team: {votes}', { votes: Object.entries(fb).map(([k, v]) => voteText(k, v)).join(t(', ')) })}</div>}
                    </div>) : <div>{t('No data for this theme and region')}</div>, wrap.current, `${th.id}:${r.id}`)}>
                  <rect x={1} y={1} width={cw - 2} height={ch - 2} rx={4} fill={fill} />
                  {c && <text x={cw / 2} y={ch / 2 + 4} textAnchor="middle" className="num"
                    style={{ fontSize: 11, fill: dark ? '#fff' : 'var(--ink-2)' }}>{fmt(n)}</text>}
                  {fb?.real > 0 && <circle cx={cw - 7} cy={7} r={3} fill="var(--ink)" stroke="var(--surface)" strokeWidth={1.5} />}
                </g>)
            })}
          </g>) })())}
      </svg>
      </div>
      {tip.node}
      <div className="legend" style={{ marginTop: 8 }}>
        <span><span className="ramp" style={{ marginInlineEnd: 5 }}>{GAP_STEPS.map((i) => <span key={i} style={{ background: `var(--gap-${i})` }} />)}</span>{t('Fewer articles than chance would explain')}</span>
        <span><span className="sw" style={{ background: 'var(--gap-1)', boxShadow: 'inset 0 0 0 1px var(--line)' }} />{t('Possibly fewer, not enough to be sure')}</span>
        <span><span className="sw" style={{ background: 'var(--gap-0)', boxShadow: 'inset 0 0 0 1px var(--line)' }} />{t('About as expected')}</span>
        <span><span className="sw" style={{ background: 'var(--gap-over)', boxShadow: 'inset 0 0 0 1px var(--line)' }} />{t('More than expected')}</span>
        <span><svg width="14" height="12" style={{ verticalAlign: -2, marginInlineEnd: 5 }}><rect width="14" height="12" fill="url(#hm-hatch)" rx="2" /></svg>{t('Not judged')}</span>
        <span>{t('Number = articles from outlets we followed all year (4 weeks)')}</span>
        <span><svg width="10" height="10" style={{ verticalAlign: -1, marginInlineEnd: 4 }}><circle cx="5" cy="5" r="3" fill="var(--ink)" /></svg>{t('a journalist marked it a real gap')}</span>
      </div>
      <p className="small muted" style={{ margin: '6px 0 0' }}>{t('Red means the shortfall is larger than chance would explain. Among the red gaps on a page, about 1 in 10 will still be chance.')}</p>
    </div>
  )
}
