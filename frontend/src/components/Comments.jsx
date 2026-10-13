import { useEffect, useState } from 'react'
import { api, qs } from '../api'

const TAGS = { '': 'Comment', agree: 'Agree', disagree: 'Disagree', missing_context: 'Missing context', source_tip: 'Source tip', safety: 'Safety concern' }

export default function Comments({ objectType, objectKey }) {
  const [rows, setRows] = useState([])
  const [body, setBody] = useState('')
  const [tag, setTag] = useState('')
  const [replyTo, setReplyTo] = useState(null)
  const [err, setErr] = useState(null)
  const load = () => api('/api/comments' + qs({ object_type: objectType, object_key: objectKey })).then(setRows)
  useEffect(() => { load() }, [objectType, objectKey])

  const submit = async (e) => {
    e.preventDefault()
    if (!body.trim()) return
    try {
      await api('/api/comments', { method: 'POST', body: { object_type: objectType, object_key: objectKey, body, tag: tag || null, parent_id: replyTo } })
      setBody(''); setTag(''); setReplyTo(null); setErr(null); load()
    } catch (ex) { setErr(ex.message) }
  }
  const resolve = async (c) => { await api(`/api/comments/${c.id}`, { method: 'PATCH', body: { resolved: !c.resolved } }); load() }
  const remove = async (c) => { await api(`/api/comments/${c.id}`, { method: 'DELETE' }); load() }
  const top = rows.filter((c) => !c.parent_id)
  const kids = (id) => rows.filter((c) => c.parent_id === id)
  const one = (c, reply) => (
    <div key={c.id} className={`comment ${reply ? 'reply' : ''}`} style={c.resolved ? { opacity: 0.6 } : undefined}>
      <div className="meta">{c.deleted ? 'deleted' : c.user} · {c.at.slice(0, 16).replace('T', ' ')} {c.tag && <span className="pill">{TAGS[c.tag]}</span>} {c.resolved && <span className="pill ok">resolved</span>}</div>
      {!c.deleted && <div dir="auto" style={{ whiteSpace: 'pre-wrap' }}>{c.body}</div>}
      {!c.deleted && (
        <div className="row small">
          {!reply && <button className="btn small ghost" onClick={() => setReplyTo(c.id)}>Reply</button>}
          {!reply && <button className="btn small ghost" onClick={() => resolve(c)}>{c.resolved ? 'Reopen' : 'Resolve'}</button>}
          {c.mine && <button className="btn small ghost" onClick={() => remove(c)}>Delete</button>}
        </div>)}
      {!reply && kids(c.id).map((k) => one(k, true))}
    </div>)
  return (
    <div>
      {top.length === 0 && <p className="muted small">No comments yet. Visible to your team only.</p>}
      {top.map((c) => one(c, false))}
      <form className="form" onSubmit={submit} style={{ marginTop: 8 }}>
        {replyTo && <div className="small muted">Replying · <button type="button" className="btn small ghost" onClick={() => setReplyTo(null)}>cancel</button></div>}
        <textarea dir="auto" value={body} onChange={(e) => setBody(e.target.value)} placeholder="Add context, a source tip, or why you agree/disagree… Use @name to mention." aria-label="Comment" />
        <div className="row">
          <select value={tag} onChange={(e) => setTag(e.target.value)} aria-label="Comment type">
            {Object.entries(TAGS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <span className="spacer" />
          {err && <span className="err">{err}</span>}
          <button className="btn primary" type="submit" disabled={!body.trim()}>Post</button>
        </div>
      </form>
    </div>
  )
}
