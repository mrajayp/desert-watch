import { useEffect, useState } from 'react'
import { api, qs } from '../api'
import { useApp } from '../App'
import { N_, t } from '../i18n'

const TAGS = { '': N_('Comment'), agree: N_('Agree'), disagree: N_('Disagree'), missing_context: N_('Missing context'), source_tip: N_('Source tip'), safety: N_('Safety concern') }

export default function Comments({ objectType, objectKey }) {
  const { me } = useApp()
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
      <div className="meta">{c.deleted ? t('deleted') : <bdi>{c.user}</bdi>} · {c.at.slice(0, 16).replace('T', ' ')} {c.tag && <span className="pill">{TAGS[c.tag] && t(TAGS[c.tag])}</span>} {c.resolved && <span className="pill ok">{t('resolved')}</span>}</div>
      {!c.deleted && <div dir="auto" style={{ whiteSpace: 'pre-wrap' }}>{c.body}</div>}
      {!c.deleted && (
        <div className="row small">
          {!reply && <button className="btn small ghost" onClick={() => setReplyTo(c.id)}>{t('Reply')}</button>}
          {!reply && <button className="btn small ghost" onClick={() => resolve(c)}>{c.resolved ? t('Reopen') : t('Resolve')}</button>}
          {c.mine && <button className="btn small ghost" onClick={() => remove(c)}>{t('Delete')}</button>}
        </div>)}
      {!reply && kids(c.id).map((k) => one(k, true))}
    </div>)
  return (
    <div>
      {top.length === 0 && <p className="muted small">{t('No comments yet. Visible to your team only.')}</p>}
      {top.map((c) => one(c, false))}
      {me.role === 'viewer' ? <p className="small muted">{t('Your account is read-only, so you can’t comment. Ask an admin for contributor access.')}</p> : (
      <form className="form" onSubmit={submit} style={{ marginTop: 8 }}>
        {replyTo && <div className="small muted">{t('Replying')} · <button type="button" className="btn small ghost" onClick={() => setReplyTo(null)}>{t('cancel')}</button></div>}
        <textarea dir="auto" value={body} onChange={(e) => setBody(e.target.value)} placeholder={t('Add context, a source tip, or why you agree/disagree… Use @name to mention.')} aria-label={t('Comment')} />
        <div className="row">
          <select value={tag} onChange={(e) => setTag(e.target.value)} aria-label={t('Comment type')}>
            {Object.entries(TAGS).map(([k, v]) => <option key={k} value={k}>{t(v)}</option>)}
          </select>
          <span className="spacer" />
          {err && <span className="err">{err}</span>}
          <button className="btn primary" type="submit" disabled={!body.trim()}>{t('Post')}</button>
        </div>
      </form>)}
    </div>
  )
}
