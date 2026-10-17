import { useEffect, useState } from 'react'
import { api, qs } from '../api'
import { useApp } from '../App'
import { fmt } from '../charts/scales'
import ArticleRow from '../components/ArticleRow'
import SourceFilter from '../components/SourceFilter'
import { N_, pick, t } from '../i18n'

const PAGE = 50
const PERIODS = [[1, N_('Last 24 hours')], [7, N_('Last 7 days')], [28, N_('Last 4 weeks')], [90, N_('Last 3 months')]]
const LANGS = [['', N_('Any')], ['ar', N_('Arabic')], ['en', N_('English')]]

// Every monitored article, newest first, filterable by source, theme, place, language and words.
export default function Articles() {
  const { meta } = useApp()
  const [f, setF] = useState({ source: '', theme_id: '', region_id: '', lang: '', days: 7, q: '' })
  const [q, setQ] = useState('')
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)
  const nm = (o) => pick(o, 'name')
  const params = (offset) => qs({ ...f, limit: PAGE, offset })

  const load = async () => {
    setBusy(true)
    try { setData(await api('/api/items' + params(0))) } finally { setBusy(false) }
  }
  const more = async () => {
    setBusy(true)
    try {
      const r = await api('/api/items' + params(data.items.length))
      setData({ ...r, items: [...data.items, ...r.items] })
    } finally { setBusy(false) }
  }
  useEffect(() => { load() }, [f])
  useEffect(() => { const t = setTimeout(() => setF((x) => (x.q === q ? x : { ...x, q })), 350); return () => clearTimeout(t) }, [q])
  const set = (patch) => setF({ ...f, ...patch })

  return (
    <main className="page">
      <section className="card">
        <div className="card-head">
          <div><h2>{t('Articles')} {data && `(${fmt(data.total)})`}</h2>
            <p className="sub">{t('Everything Desert Watch has collected that passed the {country} relevance check, newest first. Use Fix on a row to correct its topic or place.', { country: pick(meta.country, 'name') })}</p></div>
        </div>
        <div className="row" style={{ gap: 10, flexWrap: 'wrap' }}>
          <select value={f.days} onChange={(e) => set({ days: +e.target.value })} aria-label={t('Period')}>
            {PERIODS.map(([d, l]) => <option key={d} value={d}>{t(l)}</option>)}</select>
          <select value={f.theme_id} onChange={(e) => set({ theme_id: e.target.value })} aria-label={t('Theme')}>
            <option value="">{t('All themes')}</option>
            {meta.themes.map((t) => <option key={t.id} value={t.id}>{nm(t)}</option>)}</select>
          <select value={f.region_id} onChange={(e) => set({ region_id: e.target.value })} aria-label={t('Place')}>
            <option value="">{t('All places')}</option>
            {meta.regions.filter((r) => r.level !== 'national').map((r) => <option key={r.id} value={r.id}>{r.level === 'macro' ? '▸ ' : ''}{nm(r)}</option>)}</select>
          <span className="seg" role="group" aria-label={t('Language')}>
            {LANGS.map(([k, l]) =>
              <button key={k} aria-pressed={f.lang === k} onClick={() => set({ lang: k })}>{t(l)}</button>)}</span>
          <input type="search" dir="auto" placeholder={t('Words in the headline')} value={q} onChange={(e) => setQ(e.target.value)} aria-label={t('Search headlines')} />
        </div>
        <SourceFilter counts={data?.by_source} value={f.source} onChange={(source) => set({ source })} />
        {!data ? <div className="empty">{t('Loading…')}</div> : data.items.length === 0 ? <div className="empty">{t('No articles match.')}</div> : (
          <>
            <ul className="list">{data.items.map((it) => <ArticleRow key={it.id} item={it} onChanged={load} />)}</ul>
            {data.items.length < data.total && (
              <div className="row" style={{ justifyContent: 'center', marginTop: 10 }}>
                <button className="btn" disabled={busy} onClick={more}>{t('Show {n} more', { n: Math.min(PAGE, data.total - data.items.length) })}</button>
              </div>)}
          </>)}
      </section>
    </main>
  )
}
