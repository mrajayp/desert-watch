import { useEffect, useState } from 'react'
import { api, qs } from '../api'
import { useApp } from '../App'
import { fmt } from '../charts/scales'
import ArticleRow from '../components/ArticleRow'
import SourceFilter from '../components/SourceFilter'

const PAGE = 50
const PERIODS = [[1, 'Last 24 hours'], [7, 'Last 7 days'], [28, 'Last 4 weeks'], [90, 'Last 3 months']]

// Every monitored article, newest first, filterable by source, theme, place, language and words.
export default function Articles() {
  const { meta, lang } = useApp()
  const [f, setF] = useState({ source: '', theme_id: '', region_id: '', lang: '', days: 7, q: '' })
  const [q, setQ] = useState('')
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)
  const nm = (o) => (lang === 'ar' ? o.name_ar : o.name_en)
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
          <div><h2>Articles {data && `(${fmt(data.total)})`}</h2>
            <p className="sub">Everything Desert Watch has collected that passed the {meta.country.name_en} relevance check, newest first. Use Fix on a row to correct its topic or place.</p></div>
        </div>
        <div className="row" style={{ gap: 10, flexWrap: 'wrap' }}>
          <select value={f.days} onChange={(e) => set({ days: +e.target.value })} aria-label="Period">
            {PERIODS.map(([d, l]) => <option key={d} value={d}>{l}</option>)}</select>
          <select value={f.theme_id} onChange={(e) => set({ theme_id: e.target.value })} aria-label="Theme">
            <option value="">All themes</option>
            {meta.themes.map((t) => <option key={t.id} value={t.id}>{nm(t)}</option>)}</select>
          <select value={f.region_id} onChange={(e) => set({ region_id: e.target.value })} aria-label="Place">
            <option value="">All places</option>
            {meta.regions.filter((r) => r.level !== 'national').map((r) => <option key={r.id} value={r.id}>{r.level === 'macro' ? '▸ ' : ''}{nm(r)}</option>)}</select>
          <span className="seg" role="group" aria-label="Language">
            {[['', 'Any'], ['ar', 'Arabic'], ['en', 'English']].map(([k, l]) =>
              <button key={k} aria-pressed={f.lang === k} onClick={() => set({ lang: k })}>{l}</button>)}</span>
          <input type="search" dir="auto" placeholder="Words in the headline" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search headlines" />
        </div>
        <SourceFilter counts={data?.by_source} value={f.source} onChange={(source) => set({ source })} />
        {!data ? <div className="empty">Loading…</div> : data.items.length === 0 ? <div className="empty">No articles match.</div> : (
          <>
            <ul className="list">{data.items.map((it) => <ArticleRow key={it.id} item={it} onChanged={load} />)}</ul>
            {data.items.length < data.total && (
              <div className="row" style={{ justifyContent: 'center', marginTop: 10 }}>
                <button className="btn" disabled={busy} onClick={more}>Show {Math.min(PAGE, data.total - data.items.length)} more</button>
              </div>)}
          </>)}
      </section>
    </main>
  )
}
