import { useState } from 'react'
import { api } from '../api'
import { useApp } from '../App'

export default function AddArticle({ preset = {} }) {
  const { meta, closePanel, refresh } = useApp()
  const [url, setUrl] = useState('')
  const [meta2, setMeta2] = useState(null)
  const [title, setTitle] = useState('')
  const [themes, setThemes] = useState(preset.theme_ids || [])
  const [regions, setRegions] = useState(preset.region_ids || [])
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(null)
  const toggle = (arr, set, v) => set(arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v])

  const preview = async () => {
    setBusy(true); setErr(null)
    try { const m = await api('/api/items/preview', { method: 'POST', body: { url } }); setMeta2(m); setTitle(m.title || '') }
    catch (e) { setErr(`${e.message} You can still type the title yourself.`); setMeta2({}) }
    setBusy(false)
  }
  const save = async () => {
    setBusy(true); setErr(null)
    try {
      const it = await api('/api/items', { method: 'POST', body: { url, title: title || null, lang: meta2?.lang || null, published: meta2?.published || null, theme_ids: themes, region_ids: regions } })
      setDone(it); refresh()
    } catch (e) { setErr(e.message) }
    setBusy(false)
  }
  return (
    <div className="modal" role="dialog" aria-modal="true" aria-labelledby="add-title">
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h2 id="add-title" style={{ margin: 0 }}>Add an article we missed</h2>
        <button className="btn ghost" onClick={closePanel} aria-label="Close">✕</button>
      </div>
      <p className="small muted">Counts as coverage straight away and teaches the topic matcher. Good for Facebook pages, where we only see the posts Google News indexes.</p>
      {done ? (
        <div>
          <p>Added: <b dir="auto">{done.title}</b> ({done.outlet?.name}).</p>
          <div className="row"><button className="btn" onClick={() => { setDone(null); setUrl(''); setMeta2(null); setTitle('') }}>Add another</button>
            <button className="btn primary" onClick={closePanel}>Done</button></div>
        </div>
      ) : (
        <div className="form">
          <label>Link
            <div className="row" style={{ flexWrap: 'nowrap' }}>
              <input type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" style={{ flex: 1 }} />
              <button className="btn" disabled={!url || busy} onClick={preview}>Fetch</button>
            </div>
          </label>
          {meta2 && (
            <>
              <label>Title<input type="text" dir="auto" value={title} onChange={(e) => setTitle(e.target.value)} /></label>
              {meta2.site_name && <div className="small muted">{meta2.site_name} · {meta2.domain} · {meta2.lang || 'language?'} · {meta2.published?.slice(0, 10) || 'date unknown'}</div>}
              <div><div className="small">Topics</div><div className="chips">{meta.themes.map((t) =>
                <button key={t.id} className="chip" aria-pressed={themes.includes(t.id)} onClick={() => toggle(themes, setThemes, t.id)}>{t.name_en}</button>)}</div></div>
              <div><div className="small">Places (optional)</div><div className="chips">{meta.regions.filter((r) => r.level === 'district').map((r) =>
                <button key={r.id} className="chip" aria-pressed={regions.includes(r.id)} onClick={() => toggle(regions, setRegions, r.id)}>{r.name_en}</button>)}</div></div>
              <div className="row"><span className="spacer" /><button className="btn primary" disabled={busy || !themes.length || !title} onClick={save}>Add article</button></div>
            </>)}
          {err && <p className="err">{err}</p>}
        </div>)}
    </div>
  )
}
