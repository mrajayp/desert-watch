import { useState } from 'react'
import { api, qs } from '../api'
import { useApp } from '../App'
import { useApi } from '../hooks/useApi'
import { useDraft } from '../hooks/useDraft'
import { useMutation } from '../hooks/useMutation'
import { N_, t } from '../i18n'
import { ErrorBox, Loading } from './Notices'

const TAGS = { '': N_('Comment'), agree: N_('Agree'), disagree: N_('Disagree'), missing_context: N_('Missing context'), source_tip: N_('Source tip'), safety: N_('Safety concern') }

export default function Comments({ objectType, objectKey }) {
  const { can } = useApp()
  const q = useApi('/api/comments' + qs({ object_type: objectType, object_key: objectKey }))
  const rows = q.data || []
  // a half-written comment survives a language switch or a detour to another panel
  const [body, setBody, clearBody] = useDraft(`comment:${objectType}:${objectKey}`)
  const [tag, setTag] = useState('')
  const [replyTo, setReplyTo] = useState(null)
  const post = useMutation((e) => {
    e.preventDefault()
    if (!body.trim()) return Promise.resolve(null)
    return api('/api/comments', { method: 'POST', body: { object_type: objectType, object_key: objectKey, body, tag: tag || null, parent_id: replyTo } })
  }, { onSuccess: (r) => { if (r) { clearBody(); setTag(''); setReplyTo(null); q.retry() } } })
  const resolve = useMutation((c) => api(`/api/comments/${c.id}`, { method: 'PATCH', body: { resolved: !c.resolved } }), { onSuccess: q.retry })
  const remove = useMutation((c) => api(`/api/comments/${c.id}`, { method: 'DELETE' }), { onSuccess: q.retry })
  const busy = resolve.busy || remove.busy
  const top = rows.filter((c) => !c.parent_id)
  const kids = (id) => rows.filter((c) => c.parent_id === id)
  const one = (c, reply) => (
    <div key={c.id} className={`comment ${reply ? 'reply' : ''}`} style={c.resolved ? { opacity: 0.6 } : undefined}>
      <div className="meta">{c.deleted ? t('deleted') : <bdi>{c.user}</bdi>} · {c.at.slice(0, 16).replace('T', ' ')} {c.tag && <span className="pill">{TAGS[c.tag] && t(TAGS[c.tag])}</span>} {c.resolved && <span className="pill ok">{t('resolved')}</span>}</div>
      {!c.deleted && <div dir="auto" style={{ whiteSpace: 'pre-wrap' }}>{c.body}</div>}
      {!c.deleted && can && (
        <div className="row small">
          {!reply && <button className="btn small ghost" onClick={() => setReplyTo(c.id)}>{t('Reply')}</button>}
          {!reply && <button className="btn small ghost" disabled={busy} onClick={() => resolve.run(c)}>{c.resolved ? t('Reopen') : t('Resolve')}</button>}
          {c.mine && <button className="btn small ghost" disabled={busy} onClick={() => remove.run(c)}>{t('Delete')}</button>}
        </div>)}
      {!reply && kids(c.id).map((k) => one(k, true))}
    </div>)
  return (
    <div>
      {!q.data && q.error && <ErrorBox error={q.error} onRetry={q.retry} compact />}
      {!q.data && !q.error && <Loading />}
      {q.data && top.length === 0 && <p className="muted small">{t('No comments yet. Visible to your team only.')}</p>}
      {top.map((c) => one(c, false))}
      {(resolve.error || remove.error) && <ErrorBox error={resolve.error || remove.error} compact />}
      {can && (
        <form className="form" onSubmit={(e) => post.run(e)} style={{ marginTop: 8 }}>
          {replyTo && <div className="small muted">{t('Replying')} · <button type="button" className="btn small ghost" onClick={() => setReplyTo(null)}>{t('cancel')}</button></div>}
          <textarea dir="auto" value={body} onChange={(e) => setBody(e.target.value)} placeholder={t('Add context, a source tip, or why you agree/disagree…')} aria-label={t('Comment')} />
          <div className="row">
            <select value={tag} onChange={(e) => setTag(e.target.value)} aria-label={t('Comment type')}>
              {Object.entries(TAGS).map(([k, v]) => <option key={k} value={k}>{t(v)}</option>)}
            </select>
            <span className="spacer" />
            {post.error && <ErrorBox error={post.error} compact />}
            <button className="btn primary" type="submit" disabled={!body.trim() || post.busy}>{t('Post')}</button>
          </div>
        </form>)}
    </div>
  )
}
