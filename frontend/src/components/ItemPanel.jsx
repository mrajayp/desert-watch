import { useEffect, useState } from 'react'
import { api, dwell } from '../api'
import { useApp } from '../App'
import Comments from './Comments'

const DIMS = [
  ['accuracy', 'Accuracy', ['Doubtful', 'Mostly sound', 'Solid']],
  ['depth', 'Depth', ['Surface / rewrite', 'Some reporting', 'In-depth']],
  ['local_sourcing', 'Local voices', ['None', 'Some', 'Central']],
]

export default function ItemPanel({ id }) {
  const { closePanel, openOutlet } = useApp()
  const [it, setIt] = useState(null)
  const [form, setForm] = useState({ accuracy: 0, depth: 0, local_sourcing: 0, note: '' })
  const [saved, setSaved] = useState(false)
  const load = () => api(`/api/items/${id}`).then((x) => { setIt(x); if (x.assessments.mine) setForm({ ...x.assessments.mine, note: x.assessments.mine.note || '' }) })
  useEffect(() => { load() }, [id])
  useEffect(() => dwell('item', id), [id])
  if (!it) return <aside className="drawer"><div className="empty">Loading…</div></aside>
  const save = async () => {
    await api(`/api/items/${id}/assessment`, { method: 'POST', body: { ...form, note: form.note || null } })
    setSaved(true); load()
  }
  const a = it.assessments
  return (
    <aside className="drawer" aria-label="Article">
      <div className="row" style={{ justifyContent: 'space-between', flexWrap: 'nowrap' }}>
        <h2 dir="auto" style={{ margin: 0, fontSize: 17 }}>{it.title}</h2>
        <button className="btn ghost" onClick={closePanel} aria-label="Close">✕</button>
      </div>
      <p className="small muted">{it.published_at.slice(0, 10)} · <button className="btn small ghost" style={{ padding: 0 }} onClick={() => it.outlet && openOutlet(it.outlet.id)}>{it.outlet?.name}</button> · <a href={it.url} target="_blank" rel="noreferrer noopener">open article ↗</a></p>
      {it.snippet && <p dir="auto">{it.snippet}</p>}
      <h3>Your assessment</h3>
      {DIMS.map(([k, label, opts]) => (
        <div key={k} className="row" style={{ marginBottom: 6 }}>
          <span style={{ width: 100 }}>{label}</span>
          <span className="seg" role="radiogroup" aria-label={label}>
            {opts.map((o, i) => <button key={o} role="radio" aria-checked={form[k] === i + 1} aria-pressed={form[k] === i + 1} onClick={() => { setSaved(false); setForm({ ...form, [k]: i + 1 }) }}>{o}</button>)}
          </span>
        </div>))}
      <textarea dir="auto" placeholder="Optional note: what’s missing, what’s wrong, who should have been quoted…" value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
      <div className="row" style={{ marginTop: 6 }}>
        <button className="btn primary" disabled={!form.accuracy || !form.depth || !form.local_sourcing} onClick={save}>Save assessment</button>
        {saved && <span className="small muted">Saved</span>}
      </div>
      <p className="small muted">Team average ({a.count}): accuracy {a.accuracy ?? '–'}, depth {a.depth ?? '–'}, local voices {a.local_sourcing ?? '–'} (scale 1–3). Feeds each outlet’s quality score.</p>
      <h3>Discussion</h3>
      <Comments objectType="item" objectKey={String(id)} />
    </aside>
  )
}
