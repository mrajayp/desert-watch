// Theme × region grid. Fill = gap (red ramp from meta.red_from); striped = not judged;
// each cell also prints the count the score used (articles, from the outlets followed all year) so the
// score is never a black box; the tooltip adds the all-source count when it differs.
import { useRef } from 'react'
import { GAP_STEPS, fmt, gapFill, gapLabel } from './scales'
import { HatchDefs, fitLabel, groupedRows, themeLabel, useSize, useTooltip } from './util'
import { WarningPills } from '../components/Warnings'
import { pick, t } from '../i18n'

// vote codes from the API (real / covered / not_newsworthy)
const voteText = (k, v) => (k === 'real' ? t('{n} real', { n: v }) : k === 'covered' ? t('{n} covered', { n: v })
  : k === 'not_newsworthy' ? t('{n} not newsworthy', { n: v }) : `${v} ${k.replace('_', ' ')}`)

// red: meta.red_from (gapFill/gapLabel fall back to their default until it is known)
export default function Heatmap({ themes, regions, cells, onSelect, svgRef, unit = 'need', lang = 'en', feedback = {}, red }) {
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
  return (
    <div ref={wrap} className="viz" onMouseLeave={tip.hide}>
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
              const dark = c && !c.insufficient && c.gap >= 1.0
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
                      <div>{gapLabel(c.insufficient ? null : c.gap, red)}</div>
                      <WarningPills codes={c.flags} block />
                      {fb && <div className="small muted" style={{ marginTop: 4 }}>{t('Team: {votes}', { votes: Object.entries(fb).map(([k, v]) => voteText(k, v)).join(t(', ')) })}</div>}
                    </div>) : <div>{t('No data for this theme and region')}</div>, wrap.current)}>
                  <rect x={1} y={1} width={cw - 2} height={ch - 2} rx={4} fill={fill} />
                  {c && <text x={cw / 2} y={ch / 2 + 4} textAnchor="middle" className="num"
                    style={{ fontSize: 11, fill: dark ? '#fff' : 'var(--ink-2)' }}>{fmt(n)}</text>}
                  {fb?.real > 0 && <circle cx={cw - 7} cy={7} r={3} fill="var(--ink)" stroke="var(--surface)" strokeWidth={1.5} />}
                </g>)
            })}
          </g>) })())}
      </svg>
      {tip.node}
      <div className="legend" style={{ marginTop: 8 }}>
        <span>{t('Under-coverage')} <span className="ramp">{GAP_STEPS.map((i) => <span key={i} style={{ background: `var(--gap-${i})` }} />)}</span></span>
        <span><svg width="14" height="12" style={{ verticalAlign: -2, marginInlineEnd: 5 }}><rect width="14" height="12" fill="url(#hm-hatch)" rx="2" /></svg>{t('Not judged')}</span>
        <span>{t('Number = articles from outlets we followed all year (4 weeks)')}</span>
        <span><svg width="10" height="10" style={{ verticalAlign: -1, marginInlineEnd: 4 }}><circle cx="5" cy="5" r="3" fill="var(--ink)" /></svg>{t('a journalist marked it a real gap')}</span>
      </div>
    </div>
  )
}
