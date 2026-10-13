import { useEffect, useMemo, useRef, useState } from 'react'
import { api, qs } from '../api'
import { useApp } from '../App'
import Filters from '../components/Filters'
import ClusterMap, { ClusterDistrictTable, ClusterLegendTable } from '../charts/ClusterMap'
import { ClusterMultiples, ClusterSummary } from '../charts/ClusterViews'
import { MixBar } from '../charts/Balance'
import { DIMENSIONS, categoryColor, fmt } from '../charts/scales'
import { ExportMenu } from '../charts/util'

export default function Outlets() {
  const { meta, filters, openOutlet, openGap, version, lang } = useApp()
  const [rows, setRows] = useState([])
  const [network, setNetwork] = useState(null)
  const [show, setShow] = useState({ similar: false, syndication: true })
  const [clusters, setClusters] = useState(null)
  const [highlight, setHighlight] = useState(null)
  const [view, setView] = useState('summary')
  const [periods, setPeriods] = useState(null)
  const tableRef = useRef(null)
  const [q, setQ] = useState('')
  const [onlyUnclassified, setOnlyUnclassified] = useState(false)
  const svg = useRef(null)
  useEffect(() => { api('/api/outlets' + qs({ days: 84, min_articles: 1 })).then(setRows) }, [version])
  useEffect(() => { api('/api/network' + qs({ week: filters.week, weeks: 12 })).then(setNetwork) }, [filters.week, version])
  useEffect(() => { api('/api/clusters').then(setClusters); api('/api/clusters/periods').then(setPeriods) }, [version])
  const dim = filters.colorBy
  const mix = useMemo(() => {
    const m = {}
    for (const r of rows) { const v = r.categories[dim]?.value || 'unknown'; m[v] = (m[v] || 0) + r.articles }
    return m
  }, [rows, dim])
  const caption = `Source: Desert Watch, ${rows.length} monitored outlets, 12 weeks to ${filters.week}. Not a census of ${meta.country.name_en} media.
` +
    'Position = similarity of theme specialisation (assessed); clusters = Louvain communities (assessed); reprint arrows = headline overlap >= 75% within 48h, 2+ times (observed).'
  const shown = rows.filter((r) => (!q || r.name.toLowerCase().includes(q.toLowerCase()) || r.domain.includes(q.toLowerCase()))
    && (!onlyUnclassified || !r.categories.scope))
  return (
    <>
      <Filters showWeek />
      <main className="page">
        <div className="grid two">
          <section className="card" style={view === 'time' ? { gridColumn: '1 / -1' } : undefined}>
            <div className="card-head">
              <div><h2>Coverage clusters</h2>
                <p className="sub">{{
                  summary: 'One circle per cluster of outlets that over-cover the same themes; arrows show whose headlines get republished by whom.',
                  outlets: 'Outlets sit near outlets that over-cover the same themes; colour and tag = cluster. Arrows: another outlet published a near-identical headline later, 2+ times.',
                  time: 'The same outlets in the same places, in consecutive 4-week periods. Watch which clusters grow, shrink or fall silent.',
                }[view]} 12 weeks.</p></div>
              <div className="row">
                <span className="seg" role="group" aria-label="Cluster view">
                  {[['summary', 'Summary'], ['outlets', 'Outlets'], ['time', 'Over time']].map(([k, l]) =>
                    <button key={k} aria-pressed={view === k} onClick={() => setView(k)}>{l}</button>)}
                </span>
                {view === 'outlets' && <>
                  <button className="btn small" aria-pressed={show.syndication} onClick={() => setShow({ ...show, syndication: !show.syndication })}>Reprints</button>
                  <button className="btn small" aria-pressed={show.similar} onClick={() => setShow({ ...show, similar: !show.similar })}>Similarity links</button>
                </>}
                <ExportMenu svgRef={svg} title={`Coverage clusters among outlets covering ${meta.country.name_en}${view === 'time' ? ' — 4-week periods' : ''}`} filename={`coverage-clusters-${view}`} caption={caption} />
              </div>
            </div>
            {view === 'summary' && <ClusterSummary network={network} clusters={clusters?.clusters || []} themes={meta.themes} lang={lang} svgRef={svg}
              onOpenCluster={(rank) => { setHighlight(rank); setView('outlets') }} />}
            {view === 'outlets' && <ClusterMap network={network} clusters={clusters?.clusters || []} showReprints={show.syndication} showSimilarity={show.similar}
              lang={lang} svgRef={svg} highlight={highlight} setHighlight={setHighlight} onSelectOutlet={(n) => openOutlet(+n.id.slice(2))} />}
            {view === 'time' && <ClusterMultiples network={network} clusters={clusters?.clusters || []} periods={periods} lang={lang} svgRef={svg} />}
          </section>
          <section className="card">
            <h2>Clusters</h2>
            <p className="sub">Hover a row to highlight it on the map. Names are generated from each cluster’s most over-covered themes, compared with all monitored outlets.</p>
            {clusters && <ClusterLegendTable clusters={clusters.clusters} themes={meta.themes} highlight={highlight} setHighlight={setHighlight} lang={lang} />}
            <h3>Share of coverage by {DIMENSIONS[dim].label.toLowerCase()}</h3>
            <MixBar parts={mix} labels={DIMENSIONS[dim].values}
              colors={Object.fromEntries(Object.keys(DIMENSIONS[dim].values).map((v) => [v, categoryColor(dim, v)]))} height={14} />
          </section>
        </div>
        <section className="card" style={{ marginTop: 16 }}>
          <div className="card-head">
            <div><h2>Which clusters cover which districts</h2>
              <p className="sub">Share of each cluster’s articles that name the district. Rows of dots are districts no cluster writes about — candidate deserts. Click a district to open it.</p></div>
          </div>
          {clusters && <ClusterDistrictTable clusters={clusters.clusters} districts={clusters.districts} regions={meta.regions} lang={lang} highlight={highlight}
            onSelectDistrict={(rid) => openGap(meta.themes[0].id, rid, { from: 'cluster_table' })} />}
        </section>
        <section className="card" style={{ marginTop: 16 }}>
          <div className="card-head">
            <h2>Outlets ({shown.length})</h2>
            <div className="row">
              <input type="text" placeholder="Search name or domain" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search outlets" />
              <label className="small row"><input type="checkbox" checked={onlyUnclassified} onChange={(e) => setOnlyUnclassified(e.target.checked)} />unclassified only</label>
            </div>
          </div>
          <div className="scroll">
            <table className="data">
              <thead><tr><th>Outlet</th><th className="num">Articles (12 wk)</th><th>Arabic share</th><th>Base</th><th>Scope</th><th>Alignment</th><th>Quality</th><th /></tr></thead>
              <tbody>{shown.map((r) => {
                const total = Object.values(r.lang_mix).reduce((a, b) => a + b, 0) || 1
                return (
                  <tr key={r.id}>
                    <td><b>{r.name}</b><div className="small muted">{r.domain}</div></td>
                    <td className="num">{fmt(r.articles)}</td>
                    <td className="num">{Math.round(((r.lang_mix.ar || 0) / total) * 100)}%</td>
                    <td>{r.base_city || r.base_country || <span className="muted">–</span>}</td>
                    <td>{r.categories.scope ? DIMENSIONS.scope.values[r.categories.scope.value] : <span className="muted">–</span>}</td>
                    <td>{r.categories.alignment ? <>{DIMENSIONS.alignment.values[r.categories.alignment.value]} <span className="pill">{r.categories.alignment.confidence}</span></> : <span className="muted">–</span>}</td>
                    <td className="small">{r.quality ? `${r.quality.accuracy}/${r.quality.depth}/${r.quality.local_sourcing} (n=${r.quality.n})` : '–'}</td>
                    <td><button className="btn small" onClick={() => openOutlet(r.id)}>Open{r.pending_changes ? ` · ${r.pending_changes} pending` : ''}</button></td>
                  </tr>)
              })}</tbody>
            </table>
          </div>
        </section>
      </main>
    </>
  )
}
