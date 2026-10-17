// Feedback box at the bottom of every page: suggestions, questions and problems, tied to the
// page they were raised on. Admins answer them in Admin -> Feedback; replies show up here.
import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { api, qs } from '../api'
import { t } from '../i18n'

const N_ = (s) => s // marks English for the catalogue; translated with t() when shown
const KINDS = [['suggestion', N_('Suggest a feature')], ['question', N_('Ask a question')], ['problem', N_('Report a problem')]]
const KIND_WORD = { suggestion: N_('suggestion'), question: N_('question'), problem: N_('problem') }
const STATUS = { new: N_('received'), answered: N_('answered'), planned: N_('planned'), done: N_('done'), closed: N_('closed') }

export default function PageFeedback() {
  const loc = useLocation()
  const page = loc.pathname
  const [kind, setKind] = useState('suggestion')
  const [body, setBody] = useState('')
  const [mine, setMine] = useState([])
  const [msg, setMsg] = useState(null)
  const [open, setOpen] = useState(false)
  const load = () => api('/api/feedback/mine' + qs({ page })).then(setMine).catch(() => {})
  useEffect(() => { load(); setMsg(null) }, [page])
  const send = async (e) => {
    e.preventDefault()
    try {
      await api('/api/feedback', { method: 'POST', body: { page, kind, body } })
      setBody(''); setMsg(t('Thanks, sent to the admins.')); load()
    } catch (ex) { setMsg(ex.message) }
  }
  return (
    <section className="page-feedback" aria-label={t('Suggestions and questions')}>
      <div className="page-feedback-inner">
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <div>
            <b>{t('Ideas or questions about this page?')}</b>
            <span className="small muted"> {t('Suggest new functionality, ask how something works, or report a problem.')}</span>
          </div>
          <button className="btn small" aria-expanded={open} onClick={() => setOpen(!open)}>{open ? t('Close') : t('Write to the team')}</button>
        </div>
        {open && (
          <form className="form" onSubmit={send} style={{ marginTop: 10 }}>
            <span className="seg" role="group" aria-label={t('Type')}>{KINDS.map(([k, l]) =>
              <button type="button" key={k} aria-pressed={kind === k} onClick={() => setKind(k)}>{t(l)}</button>)}</span>
            <textarea dir="auto" value={body} onChange={(e) => setBody(e.target.value)} maxLength={4000}
              placeholder={kind === 'question' ? t('What would you like to know?') : kind === 'problem' ? t('What happened, and what did you expect?') : t('What would make this page more useful to you?')} />
            <div className="row"><button className="btn primary" disabled={body.trim().length < 3}>{t('Send')}</button>{msg && <span className="small">{msg}</span>}</div>
          </form>)}
        {mine.length > 0 && (
          <ul className="list small" style={{ marginTop: 8 }}>{mine.slice(0, 5).map((f) => (
            <li key={f.id}><span className="pill">{KIND_WORD[f.kind] ? t(KIND_WORD[f.kind]) : f.kind}</span> <span dir="auto">{f.body}</span>
              <span className="muted"> · {STATUS[f.status] ? t(STATUS[f.status]) : f.status}</span>
              {f.reply && <div className="comment" style={{ marginTop: 4 }}><span className="meta">{t('Reply')}</span><div dir="auto">{f.reply}</div></div>}</li>))}</ul>)}
      </div>
    </section>
  )
}
