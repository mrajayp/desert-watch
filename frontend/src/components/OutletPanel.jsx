import { useEffect, useState } from 'react'
import { api, qs } from '../api'
import { useApp } from '../App'
import { DIMENSIONS } from '../charts/scales'
import Comments from './Comments'
import ArticleRow from './ArticleRow'
import OutletReach from './OutletReach'

export default function OutletPanel({ id }) {
  const { me, meta, closePanel, refresh } = useApp()
  const [o, setO] = useState(null)
  const [hist, setHist] = useState([])
  const [tax, setTax] = useState(null)
  const [items, setItems] = useState(null)
  const [form, setForm] = useState({ dimension: 'alignment', value: '', confidence: 'reported', evidence_url: '', note: '' })
  const [base, setBase] = useState('')
  const [msg, setMsg] = useState(null)
  const load = async () => {
    const all = await api('/api/outlets' + qs({ days: 365 }))
    setO(all.find((x) => x.id === id))
    setHist(await api(`/api/outlets/${id}/history`))
    setItems(await api('/api/items' + qs({ outlet_id: id, days: 84, limit: 20 })))
  }
  useEffect(() => { load(); api('/api/outlets/taxonomy').then(setTax) }, [id])
  if (!o || !tax) return <aside className="drawer"><div className="empty">Loading…</div></aside>
  const dim = tax.dimensions.find((d) => d.key === form.dimension)
  const submit = async (e) => {
    e.preventDefault()
    try {
      const r = await api(`/api/outlets/${id}/categories`, { method: 'POST', body: { ...form, note: form.note || null } })
      setMsg(r.status === 'active' ? 'Applied.' : 'Proposed — an admin will review it.')
      setForm({ ...form, value: '', evidence_url: '', note: '' }); load(); refresh()
    } catch (ex) { setMsg(ex.message) }
  }
  const review = async (cid, approve) => { await api(`/api/outlets/categories/${cid}/review`, { method: 'POST', body: { approve } }); load(); refresh() }
  const setLocation = async () => {
    const isCity = base in (meta.country.cities || {})
    await api(`/api/outlets/${id}`, { method: 'PATCH', body: isCity ? { base_city: base } : { base_country: base } })
    setBase(''); load(); refresh()
  }
  const label = (d, v) => DIMENSIONS[d]?.values?.[v] || v
  return (
    <aside className="drawer" aria-label="Outlet">
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <div><h2 style={{ margin: 0 }}>{o.name}</h2><div className="small muted">{o.domain} · {o.created_via === 'auto' ? 'found automatically' : 'seeded'} · {o.articles} articles (12 months)</div></div>
        <button className="btn ghost" onClick={closePanel} aria-label="Close">✕</button>
      </div>
      <h3>Current profile</h3>
      <table className="data"><tbody>
        <tr><th>Base</th><td>{o.base_city || o.base_country || <span className="muted">not set</span>}</td></tr>
        {tax.dimensions.map((d) => {
          const c = o.categories[d.key]
          return <tr key={d.key}><th>{d.name}{d.contested && <span className="muted small"> (contested)</span>}</th>
            <td>{c ? <>{d.third_party && <span className="muted small">as published: </span>}{label(d.key, c.value)} <span className="pill">{c.confidence}</span>{' '}
              {c.evidence_url?.startsWith('http') ? <a className="small" href={c.evidence_url} target="_blank" rel="noreferrer noopener">evidence ↗</a>
                : <span className="small muted">source: Social Media scraped data (2023–24)</span>}</> : <span className="muted">unclassified</span>}</td></tr>
        })}
        {o.monitored === false && <tr><th>Collection</th><td><span className="pill">partly seen</span> <span className="small muted">Facebook page: we only see the posts Google News indexes</span></td></tr>}
        {o.external?.social_media_scrape && <tr><th>Social-media scrape</th><td className="small">
          {Object.entries(o.external.social_media_scrape).filter(([k]) => !['source', 'period', 'link', 'kind'].includes(k)).map(([k, v]) => `${k.replace('_', ' ')} ${Number(v).toLocaleString()}`).join(' · ')}
          <div className="muted">Social Media scraped data, {o.external.social_media_scrape.period?.from} to {o.external.social_media_scrape.period?.to}</div></td></tr>}
        {o.quality && <tr><th>Quality (team)</th><td>accuracy {o.quality.accuracy} · depth {o.quality.depth} · local voices {o.quality.local_sourcing} <span className="muted">(n={o.quality.n})</span></td></tr>}
      </tbody></table>
      <OutletReach id={id} />

      {me.role === 'admin' && (
        <div className="row" style={{ marginTop: 10 }}>
          <input list="cities" placeholder="Base city or country" value={base} onChange={(e) => setBase(e.target.value)} />
          <datalist id="cities">{Object.keys(meta.country.cities || {}).map((c) => <option key={c} value={c} />)}</datalist>
          <button className="btn small" disabled={!base} onClick={setLocation}>Set base</button>
        </div>)}

      <h3>{me.role === 'admin' ? 'Set a category' : 'Suggest a category'}</h3>
      <form className="form" onSubmit={submit}>
        <div className="row">
          <select value={form.dimension} onChange={(e) => setForm({ ...form, dimension: e.target.value, value: '' })} aria-label="Dimension">
            {tax.dimensions.map((d) => <option key={d.key} value={d.key}>{d.name}</option>)}</select>
          <select value={form.value} onChange={(e) => setForm({ ...form, value: e.target.value })} aria-label="Value" required>
            <option value="">choose…</option>{dim.values.map((v) => <option key={v} value={v}>{label(dim.key, v)}</option>)}</select>
          <select value={form.confidence} onChange={(e) => setForm({ ...form, confidence: e.target.value })} aria-label="Confidence">
            {tax.confidence_levels.map((c) => <option key={c} value={c}>{c}</option>)}</select>
        </div>
        <input type="url" required placeholder="Evidence link (study, ownership record, outlet’s own page…)" value={form.evidence_url} onChange={(e) => setForm({ ...form, evidence_url: e.target.value })} />
        <textarea dir="auto" placeholder="Note (optional)" value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
        {dim.contested && <p className="small muted">Contested label: quote the source’s own wording in the note. Shown as “classified as … per [source]”, team-only.</p>}
        <div className="row"><button className="btn primary" disabled={!form.value || !form.evidence_url}>{me.role === 'admin' ? 'Apply' : 'Propose'}</button>{msg && <span className="small">{msg}</span>}</div>
      </form>

      <h3>History</h3>
      {hist.length === 0 ? <p className="muted small">No category records.</p> : (
        <ul className="list small">{hist.map((h) => (
          <li key={h.id}><b>{tax.dimensions.find((d) => d.key === h.dimension)?.name}</b>: {label(h.dimension, h.value)} · {h.confidence} · {h.status}
            · {h.valid_from}{h.valid_to ? ` → ${h.valid_to}` : ' → now'} {h.set_by && `· by ${h.set_by}`} · <a href={h.evidence_url} target="_blank" rel="noreferrer noopener">evidence</a>
            {h.note && <div className="muted" dir="auto">{h.note}</div>}
            {h.status === 'proposed' && me.role === 'admin' && <div className="row"><button className="btn small" onClick={() => review(h.id, true)}>Approve</button><button className="btn small ghost" onClick={() => review(h.id, false)}>Reject</button></div>}
          </li>))}</ul>)}
      <h3>Recent articles</h3>
      <ul className="list">{items?.items.map((it) => <ArticleRow key={it.id} item={it} onChanged={load} />)}</ul>
      <h3>Discussion</h3>
      <Comments objectType="outlet" objectKey={String(id)} />
    </aside>
  )
}
