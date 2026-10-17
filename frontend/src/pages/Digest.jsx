import { Fragment, useEffect, useState } from 'react'
import { api } from '../api'
import { useApp } from '../App'
import { N_, fmtDate, getLang, isAr, t } from '../i18n'

// digest status codes from the API (shown for anything but 'ok')
const STATUS = { error: N_('error'), refused: N_('refused') }
const status = (s) => t(STATUS[s] || s)
// a week start (YYYY-MM-DD): as is in English, with Libyan month names in Arabic
const day = (d) => (isAr() ? fmtDate(d) : d)

// Minimal, safe Markdown: headings, bullets, paragraphs, **bold**, *italic*. Text only, no HTML.
function inline(text) {
  const parts = []
  const re = /(\*\*[^*]+\*\*|\*[^*]+\*)/g
  let last = 0, m
  while ((m = re.exec(text))) {
    if (m.index > last) parts.push(text.slice(last, m.index))
    const tok = m[0]
    parts.push(tok.startsWith('**') ? <strong key={m.index}>{tok.slice(2, -2)}</strong> : <em key={m.index}>{tok.slice(1, -1)}</em>)
    last = m.index + tok.length
  }
  if (last < text.length) parts.push(text.slice(last))
  return parts
}

export function Markdown({ text }) {
  const blocks = []
  let list = null
  for (const raw of (text || '').split('\n')) {
    const line = raw.trimEnd()
    const bullet = line.match(/^\s*[-*]\s+(.*)/)
    if (bullet) { (list ||= []).push(bullet[1]); continue }
    if (list) { blocks.push({ ul: list }); list = null }
    if (!line.trim()) continue
    const h = line.match(/^(#{1,4})\s+(.*)/)
    blocks.push(h ? { h: h[1].length, text: h[2] } : { p: line })
  }
  if (list) blocks.push({ ul: list })
  return (
    <div className="md" dir="auto">
      {blocks.map((b, i) => (
        <Fragment key={i}>
          {b.h && (b.h <= 2 ? <h3 style={{ marginTop: 18 }}>{inline(b.text)}</h3> : <h4>{inline(b.text)}</h4>)}
          {b.p && <p>{inline(b.p)}</p>}
          {b.ul && <ul>{b.ul.map((li, j) => <li key={j}>{inline(li)}</li>)}</ul>}
        </Fragment>))}
    </div>
  )
}

export default function DigestPage() {
  const { me } = useApp()
  const [list, setList] = useState(null)
  const [cur, setCur] = useState(null)
  const [showFacts, setShowFacts] = useState(false)
  const [msg, setMsg] = useState(null)
  const load = () => api('/api/digests').then((l) => {
    setList(l)
    const first = l.find((d) => d.status === 'ok') || l[0]
    if (first) api(`/api/digests/${first.id}`).then(setCur)
  })
  useEffect(() => { load() }, [])
  const open = (id) => api(`/api/digests/${id}`).then((d) => { setCur(d); setShowFacts(false) })
  const regenerate = async () => {
    await api('/api/admin/run/digest', { method: 'POST' })
    setMsg(t('Generating… refresh in a minute. (Needs the ANTHROPIC_API_KEY secret on the server.)'))
  }
  return (
    <main className="page">
      <div className="grid two">
        <section className="card">
          {!list ? <div className="empty">{t('Loading…')}</div> : !cur ? (
            <div className="empty">
              {t('No digest yet. It is written about the week before, on Monday at 06:00 UTC. If Sunday’s Wikipedia views are not in by then, it tries again each morning up to Thursday. It needs an Anthropic API key on the server.')}
              {me.role === 'admin' && <><br /><br /><button className="btn" onClick={regenerate}>{t('Generate now')}</button></>}
              {msg && <p className="small">{msg}</p>}
            </div>
          ) : (
            <>
              <div className="card-head">
                <div><h2>{t('Weekly brief · week of {week}', { week: day(cur.week_start) })}</h2>
                  <p className="sub">{t('Written by {model} from the facts below · {time} UTC', { model: cur.model, time: cur.created_at.slice(0, 16).replace('T', ' ') })}
                    {cur.usage?.input_tokens ? <> · {t('{n} tokens', { n: cur.usage.input_tokens + cur.usage.output_tokens })}</> : ''}</p></div>
                {me.role === 'admin' && <button className="btn small" onClick={regenerate}>{t('Regenerate')}</button>}
              </div>
              {msg && <p className="small">{msg}</p>}
              {cur.status === 'ok' && cur.lang && cur.lang !== getLang() &&
                <p className="small muted">{t('This brief was written before briefs were produced in Arabic too, so it is shown in English.')}</p>}
              {cur.status === 'ok' ? <Markdown text={cur.content_md} /> : <div className="banner">{status(cur.status)}: {cur.error}</div>}
              <p className="small muted" style={{ marginTop: 16 }}>{t('AI-written from the tool’s own counts; every number should appear in the facts. Check before quoting.')}</p>
              <button className="btn small ghost" onClick={() => setShowFacts(!showFacts)}>{showFacts ? t('Hide the facts it was given') : t('Show the facts it was given')}</button>
              {showFacts && <pre className="mono" style={{ whiteSpace: 'pre-wrap', maxHeight: 420, overflow: 'auto', background: 'var(--surface-2)', padding: 10, borderRadius: 6 }}>{JSON.stringify(cur.facts, null, 2)}</pre>}
            </>)}
        </section>
        <section className="card">
          <h2>{t('Archive')}</h2>
          <ul className="list">{(list || []).map((d) => (
            <li key={d.id}><button className="btn ghost" aria-pressed={cur?.id === d.id} onClick={() => open(d.id)}>{t('Week of {week}', { week: day(d.week_start) })}</button>
              <span className="small muted"> {d.status !== 'ok' && status(d.status)}</span></li>))}</ul>
          {list && !list.length && <p className="muted small">{t('No briefs yet.')}</p>}
        </section>
      </div>
    </main>
  )
}
