import { useMemo, useRef, useState } from 'react'
import BlindSpots from '../components/BlindSpots'
import AiAnswers from '../components/AiAnswers'
import { qs } from '../api'
import { useApp } from '../App'
import Filters from '../components/Filters'
import { ErrorBox } from '../components/Notices'
import ClusterMap, { ClusterDistrictTable, ClusterLegendTable } from '../charts/ClusterMap'
import { ClusterMultiples, ClusterSummary } from '../charts/ClusterViews'
import { MixBar } from '../charts/Balance'
import { DIMENSIONS, categoryColor, fmt } from '../charts/scales'
import { weekEnd } from '../charts/trendText'
import { ExportMenu } from '../charts/util'
import { useApi } from '../hooks/useApi'
import { usePageTitle } from '../hooks/usePageTitle'
import { fmtDate, fmtNum, pick, t } from '../i18n'
import { countryName } from '../charts/RegionalNetwork'

const N_ = (s) => s // marks English for the catalogue; translated with t() when shown
// a decimal as the API sends it (4.2), with the interface language's decimal mark
const num = (v) => fmtNum(v, { useGrouping: false })

// confidence codes from the API, shown as they are in English. DIMENSIONS labels are already
// in the interface language (charts/scales.js).
const CONFIDENCE = { reported: N_('reported'), likely: N_('likely'), disputed: N_('disputed'), unverified: N_('unverified') }

export default function Outlets() {
  const { meta, filters, openOutlet, openArticles, version, lang } = useApp()
  usePageTitle(t('Outlets'))
  const rowsQ = useApi('/api/outlets' + qs({ days: 84, min_articles: 1 }), { deps: [version] })
  const rows = rowsQ.data || []
  const networkQ = useApi('/api/network' + qs({ week: filters.week, weeks: 12 }), { deps: [version] })
  const network = networkQ.data
  const clustersQ = useApi('/api/clusters', { deps: [version] })
  const clusters = clustersQ.data
  const periodsQ = useApi('/api/clusters/periods', { deps: [version] })
  const periods = periodsQ.data
  const loadError = rowsQ.error || networkQ.error || clustersQ.error || periodsQ.error
  const retryLoads = () => { rowsQ.retry(); networkQ.retry(); clustersQ.retry(); periodsQ.retry() }
  const [show, setShow] = useState({ similar: false, syndication: true })
  const [highlight, setHighlight] = useState(null)
  const [view, setView] = useState('summary')
  const [q, setQ] = useState('')
  const [onlyUnclassified, setOnlyUnclassified] = useState(false)
  const svg = useRef(null)
  // a district in the cluster table has no theme: open its articles for the same 12 weeks, not an unscored gap
  const openDistrict = (rid) => openArticles({ title: pick(meta.regions.find((r) => r.id === rid), 'name'), from: 'cluster_table',
    subtitle: t('Monitored articles naming this district, 12 weeks.'), query: { region_id: rid, days: 84 } })
  const dim = filters.colorBy
  const mix = useMemo(() => {
    const m = {}
    for (const r of rows) { const v = r.categories[dim]?.value || 'unknown'; m[v] = (m[v] || 0) + r.articles }
    return m
  }, [rows, dim])
  const country = pick(meta.country, 'name')
  const caption = t('Source: Desert Watch, {n} monitored outlets, 12 weeks to {week}. Not a census of {country} media.', { n: rows.length, week: filters.week ? fmtDate(weekEnd(filters.week)) : '', country }) + '\n' +
    t('Position = similarity of theme specialisation (assessed); clusters = Louvain communities (assessed); reprint arrows = headline overlap >= 75% within 48h, 2+ times (observed).')
  const shown = rows.filter((r) => (!q || r.name.toLowerCase().includes(q.toLowerCase()) || r.domain.includes(q.toLowerCase()))
    && (!onlyUnclassified || !r.categories.scope))
  return (
    <>
      {/* this page reads the week and the outlet colouring only; the lens and theme would be ignored */}
      <Filters showLens={false} showTheme={false} />
      <main className="page">
        {loadError && <ErrorBox error={loadError} onRetry={retryLoads} />}
        <div className="grid two">
          <section className="card" style={view === 'time' ? { gridColumn: '1 / -1' } : undefined}>
            <div className="card-head">
              <div><h2>{t('Coverage clusters')}</h2>
                <p className="sub">{{
                  summary: t('One circle per cluster of outlets that over-cover the same themes; arrows show whose headlines get republished by whom.'),
                  outlets: t('Outlets sit near outlets that over-cover the same themes; colour and tag = cluster. Arrows: another outlet published a near-identical headline later, 2+ times.'),
                  time: t('The same outlets in the same places, in consecutive 4-week periods. Watch which clusters grow, shrink or fall silent.'),
                }[view]} {t('12 weeks.')}</p></div>
              <div className="row">
                <span className="seg" role="group" aria-label={t('Cluster view')}>
                  {[['summary', t('Summary')], ['outlets', t('Outlets')], ['time', t('Over time')]].map(([k, l]) =>
                    <button key={k} aria-pressed={view === k} onClick={() => setView(k)}>{l}</button>)}
                </span>
                {view === 'outlets' && <>
                  <button className="btn small" aria-pressed={show.syndication} onClick={() => setShow({ ...show, syndication: !show.syndication })}>{t('Reprints')}</button>
                  <button className="btn small" aria-pressed={show.similar} onClick={() => setShow({ ...show, similar: !show.similar })}>{t('Similarity links')}</button>
                </>}
                <ExportMenu svgRef={svg} title={view === 'time' ? t('Coverage clusters among outlets covering {country} — 4-week periods', { country }) : t('Coverage clusters among outlets covering {country}', { country })} filename={`coverage-clusters-${view}`} caption={caption} />
              </div>
            </div>
            {view === 'summary' && <ClusterSummary network={network} clusters={clusters?.clusters || []} themes={meta.themes} lang={lang} svgRef={svg}
              onOpenCluster={(rank) => { setHighlight(rank); setView('outlets') }} />}
            {view === 'outlets' && <ClusterMap network={network} clusters={clusters?.clusters || []} showReprints={show.syndication} showSimilarity={show.similar}
              lang={lang} svgRef={svg} highlight={highlight} setHighlight={setHighlight} onSelectOutlet={(n) => openOutlet(+n.id.slice(2))} />}
            {view === 'time' && <ClusterMultiples network={network} clusters={clusters?.clusters || []} periods={periods} lang={lang} svgRef={svg} />}
          </section>
          <section className="card">
            <h2>{t('Clusters')}</h2>
            <p className="sub">{t('Hover a row to highlight it on the map. Names are generated from each cluster’s most over-covered themes, compared with all monitored outlets.')}</p>
            {clusters && <ClusterLegendTable clusters={clusters.clusters} themes={meta.themes} highlight={highlight} setHighlight={setHighlight} lang={lang} />}
            <h3>{t('Share of coverage by {dimension}', { dimension: DIMENSIONS[dim].label.toLowerCase() })}</h3>
            <MixBar parts={mix} labels={DIMENSIONS[dim].values}
              colors={Object.fromEntries(Object.keys(DIMENSIONS[dim].values).map((v) => [v, categoryColor(dim, v)]))} height={14} />
          </section>
        </div>
        <section className="card" style={{ marginTop: 16 }}>
          <div className="card-head">
            <div><h2>{t('Which clusters cover which districts')}</h2>
              <p className="sub">{t('Share of each cluster’s articles that name the district. Rows of dots are districts no cluster writes about — candidate deserts. Click a district to open it.')}</p></div>
          </div>
          {clusters && <ClusterDistrictTable clusters={clusters.clusters} districts={clusters.districts} regions={meta.regions} lang={lang} highlight={highlight}
            onSelectDistrict={openDistrict} />}
        </section>
        <BlindSpots />
        <AiAnswers />
        <section className="card" style={{ marginTop: 16 }}>
          <div className="card-head">
            <h2>{t('Outlets ({n})', { n: shown.length })}</h2>
            <div className="row">
              <input type="text" placeholder={t('Search name or domain')} value={q} onChange={(e) => setQ(e.target.value)} aria-label={t('Search outlets')} />
              <label className="small row"><input type="checkbox" checked={onlyUnclassified} onChange={(e) => setOnlyUnclassified(e.target.checked)} />{t('unclassified only')}</label>
            </div>
          </div>
          <div className="scroll">
            <table className="data">
              <thead><tr><th>{t('Outlet')}</th><th className="num">{t('Articles (12 wk)')}</th><th>{t('Arabic share')}</th><th>{t('Base')}</th><th>{t('Scope')}</th><th>{t('Alignment')}</th><th title={t('Social Media scraped data, Oct 2023 to Aug 2024')}>{t('Scrape 2023–24')}</th><th>{t('Quality')}</th><th /></tr></thead>
              <tbody>{shown.map((r) => {
                const total = Object.values(r.lang_mix).reduce((a, b) => a + b, 0) || 1
                return (
                  <tr key={r.id}>
                    <td><b dir="auto">{r.name}</b><div className="small muted">{r.domain}</div></td>
                    <td className="num">{fmt(r.articles)}</td>
                    <td className="num">{Math.round(((r.lang_mix.ar || 0) / total) * 100)}%</td>
                    <td>{r.base_city || countryName(r.base_country) || <span className="muted">–</span>}</td>
                    <td>{r.categories.scope ? DIMENSIONS.scope.values[r.categories.scope.value] : <span className="muted">–</span>}</td>
                    <td>{r.categories.alignment ? <>{DIMENSIONS.alignment.values[r.categories.alignment.value]} <span className="pill">{CONFIDENCE[r.categories.alignment.confidence] ? t(CONFIDENCE[r.categories.alignment.confidence]) : r.categories.alignment.confidence}</span></> : <span className="muted">–</span>}</td>
                    <td className="small">{r.external?.social_media_scrape ? <>
                      {t('{articles} art. · {engagement} FB eng.', { articles: fmt(r.external.social_media_scrape.articles), engagement: fmt(r.external.social_media_scrape.fb_engagement) })}
                      {r.categories.scrape_affiliation && <div className="muted">{t('labelled {label}', { label: r.categories.scrape_affiliation.value })} <span className="pill">{t('disputed')}</span></div>}</> : '–'}</td>
                    <td className="small">{r.quality ? `${num(r.quality.accuracy)}/${num(r.quality.depth)}/${num(r.quality.local_sourcing)} (n=${r.quality.n})` : '–'}</td>
                    <td><button className="btn small" onClick={() => openOutlet(r.id)}>{r.pending_changes ? t('Open · {n} pending', { n: r.pending_changes }) : t('Open')}</button></td>
                  </tr>)
              })}</tbody>
            </table>
          </div>
        </section>
      </main>
    </>
  )
}
