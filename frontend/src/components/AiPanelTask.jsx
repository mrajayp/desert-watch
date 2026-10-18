// Weekly task on the Contribute page: the team's own log of AI answers (the journalist panel of the
// AI answers audit, docs/research/ai_answers_audit_scope.md). The automatic audit only sees the
// developer services; here team members ask the same questions in the AI app they really use on their
// own phone and paste the source links the answer showed. The server matches the links to the outlet
// register (ai_audit/matcher.py). Only the links leave this page: the pasted text is reduced to its
// http(s) links here, so an answer pasted by mistake is never sent. Entries carry no name for anyone
// else; the author and admins can delete them. Admins can also log a supervised browser session
// (origin browser, recorded as asked from London). Results are shown per origin in the Outlets card.
import { useEffect, useState } from 'react'
import { api } from '../api'
import { useApp } from '../App'
import { fmtDate, isAr, N_, pick, t, tn } from '../i18n'

const MAX_LINKS = 30
const LANG_NAME = { ar: N_('Arabic'), en: N_('English') }
const ASKED_IN = { LY: N_('from {country}'), other: N_('from elsewhere'), London: N_('from London') }
const code = (table, k, vars) => (table[k] ? t(table[k], vars) : k)

// The web links in pasted text, each once, as they will be stored: http(s) only; trailing punctuation
// (Latin and Arabic) and an unbalanced closing bracket dropped; a Google redirect (google.com/url?q=...)
// replaced by the page it points to; a text fragment (#:~:text=..., which AI Overview links carry and
// which quotes the page, possibly a name) removed.
export function extractLinks(text) {
  const out = []
  for (let u of String(text || '').match(/https?:\/\/[^\s<>"'«»]+/gi) || []) {
    u = u.replace(/[.,;:!?،؛…]+$/u, '')
    for (const [open, close] of [['(', ')'], ['[', ']']]) {
      while (u.endsWith(close) && u.split(close).length > u.split(open).length) u = u.slice(0, -1)
    }
    try {
      const p = new URL(u)
      if (/(^|\.)google\.[a-z.]+$/i.test(p.hostname) && p.pathname === '/url') {
        const inner = p.searchParams.get('q') || p.searchParams.get('url')
        if (inner && /^https?:\/\//i.test(inner)) u = inner
      }
    } catch { /* not a URL the browser can read: kept as written, the server decides */ }
    u = u.replace(/#:~:text=.*$/, '').replace(/:~:text=.*$/, '')
    if (u.length > 10 && !out.includes(u)) out.push(u)
  }
  return out
}

// letters left once the links are taken out: more than a few words means an answer was pasted too
const extraText = (text) => String(text || '').replace(/https?:\/\/[^\s<>"'«»]+/gi, ' ').replace(/[^\p{L}]+/gu, '').length

async function copyText(s) {
  try {
    await navigator.clipboard.writeText(s)
    return true
  } catch {
    try {
      const ta = document.createElement('textarea')
      ta.value = s
      ta.setAttribute('readonly', '')
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.select()
      const ok = document.execCommand('copy')
      ta.remove()
      return ok
    } catch { return false }
  }
}

const EMPTY = { app: '', question_key: '', lang: '', asked_in: '', links: '', no_sources: false, origin: 'panel' }

export default function AiPanelTask({ n, ro: readOnly }) {
  const { meta, me } = useApp()
  const country = pick(meta?.country, 'name')
  const [d, setD] = useState(null)
  const [err, setErr] = useState(null)
  const [f, setF] = useState(() => ({ ...EMPTY, lang: isAr() ? 'ar' : 'en' }))
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState(null) // {ok: bool, text}
  const [copied, setCopied] = useState(null) // 'key:lang', or 'fail'
  const load = () => api('/api/ai-panel/week').then((r) => { setD(r); setErr(null) }).catch((e) => setErr(e.message))
  useEffect(() => { load() }, [])
  const set = (patch) => { setF({ ...f, ...patch }); setMsg(null) }

  const questions = d?.questions || []
  const apps = d?.apps || []
  const qText = (q) => (isAr() ? q.ar : q.en) || q.en || q.ar || q.key
  const qByKey = Object.fromEntries(questions.map((q, i) => [q.key, { ...q, n: i + 1 }]))
  const appLabel = (k) => apps.find((a) => a.key === k)?.label || k
  const themeName = (slug) => (slug ? pick((meta?.themes || []).find((th) => th.slug === slug), 'name') : '')
  const ro = readOnly || d?.can_log === false
  const browserOk = Boolean(d?.can_log_browser ?? me?.role === 'admin')
  const maxLinks = d?.max_links ?? MAX_LINKS
  const browser = f.origin === 'browser' && browserOk
  const found = f.no_sources ? [] : extractLinks(f.links)
  const tooMany = found.length > maxLinks
  const pastedText = !f.no_sources && extraText(f.links) > 60
  const limit = d?.limit ?? 40
  const used = d?.used ?? 0
  const full = used >= limit
  const ready = !ro && !busy && !full && f.app && f.question_key && f.lang && (browser || f.asked_in)
    && (f.no_sources || (found.length > 0 && !tooMany))

  const copy = async (q, lang) => {
    const ok = await copyText(lang === 'ar' ? q.ar : q.en)
    setCopied(ok ? `${q.key}:${lang}` : 'fail')
    setTimeout(() => setCopied((c) => (c === `${q.key}:${lang}` ? null : c)), 2000)
  }

  const send = async (e) => {
    e.preventDefault()
    if (!ready) return
    setBusy(true); setMsg(null)
    try {
      // asked_in is set to London by the server for a browser session; 'other' is only a valid placeholder
      const r = await api('/api/ai-panel/entries', { method: 'POST', body: {
        question_key: f.question_key, lang: f.lang, app: f.app, asked_in: browser ? 'other' : f.asked_in,
        no_sources: f.no_sources, links: f.no_sources ? '' : found.join('\n'), origin: browser ? 'browser' : 'panel',
      } })
      setMsg({ ok: true, text: f.no_sources ? t('Saved, with no sources shown.')
        : t('Saved. Links: {links}. Matched to an outlet: {matched}. Not in the register: {unknown}.', {
          links: r?.links ?? found.length, matched: r?.matched ?? 0, unknown: r?.unknown ?? 0 }) })
      // the same app, language and place are likely for the next question
      setF({ ...f, question_key: '', links: '', no_sources: false })
      load()
    } catch (ex) { setMsg({ ok: false, text: ex.message }) } finally { setBusy(false) }
  }

  const remove = async (id) => {
    if (!window.confirm(t('Delete this entry? Its links are taken out of the audit.'))) return
    try { await api(`/api/ai-panel/entries/${id}`, { method: 'DELETE' }); load() } catch (ex) { setMsg({ ok: false, text: ex.message }) }
  }

  const order = isAr() ? ['ar', 'en'] : ['en', 'ar']
  const mine = d?.mine || []
  const nLinks = (e) => (Array.isArray(e.links) ? e.links.length : Number(e.links) || 0)

  return (
    <section className="card" style={{ marginTop: 16 }}>
      <div className="card-head">
        <div><h2>{n && <span className="muted">{n}.</span>} {t('Ask an AI assistant')}</h2>
          <p className="sub">{t('Many people now get news about {country} from AI apps. Ask one or more of this week’s questions in the AI app you use on your phone, and paste the source links the answer showed. Desert Watch matches them to the outlet register, so we can see which outlets these apps send people to. The automatic audit sees only the developer services, which can answer differently.', { country })}</p></div>
        {d && <span className="stat"><span className="v num">{used}</span><span className="l">{t('entries this week (limit {limit})', { limit })}</span></span>}
      </div>
      <div className="banner info small">{t('Ask in your own app, as you normally would. Paste only the source links, one per line. Do not paste the answer text or anything that names a private person. Your name is never shown with your entries.')}</div>
      {err && !(ro && !d) && <p className="err">{err}</p>}
      {!d ? (ro && err ? <p className="small muted">{t('Your account is read-only, so you cannot log answers yet.')}</p>
        : !err && <div className="empty">{t('Loading…')}</div>) : (
        <>
          <h3>{t('This week’s questions (from {week})', { week: fmtDate(d.week_start) })}</h3>
          <ol className="list" style={{ marginBottom: 12 }}>{questions.map((q, i) => (
            <li key={q.key}>
              <div className="small muted">{i + 1}{themeName(q.theme) && <> · {themeName(q.theme)}</>}</div>
              {order.map((lang) => (
                <div key={lang} className="row" style={{ justifyContent: 'space-between', flexWrap: 'nowrap', marginTop: 4 }}>
                  <span lang={lang} dir={lang === 'ar' ? 'rtl' : 'ltr'} style={{ minWidth: 0 }}>{lang === 'ar' ? q.ar : q.en}</span>
                  <button type="button" className="btn small" onClick={() => copy(q, lang)}
                    aria-label={lang === 'ar' ? t('Copy the question in Arabic') : t('Copy the question in English')}>
                    {copied === `${q.key}:${lang}` ? t('Copied') : t('Copy')}</button>
                </div>))}
            </li>))}</ol>
          {copied === 'fail' && <p className="small err">{t('Copy failed. Select the text and copy it by hand.')}</p>}

          {ro ? <p className="small muted">{t('Your account is read-only, so you cannot log answers yet.')}</p> : (
            <form className="form" onSubmit={send}>
              {browserOk && (
                <div className="seg" role="group" aria-label={t('How the answer was asked')} style={{ justifySelf: 'start', flexWrap: 'wrap' }}>
                  <button type="button" aria-pressed={!browser} onClick={() => set({ origin: 'panel' })}>{t('Team panel: an app on a phone')}</button>
                  <button type="button" aria-pressed={browser} onClick={() => set({ origin: 'browser' })}>{t('Supervised browser session')}</button>
                </div>)}
              <div className="row">
                <select required value={f.app} onChange={(e) => set({ app: e.target.value })} aria-label={t('App')}>
                  <option value="">{t('App…')}</option>
                  {apps.map((a) => <option key={a.key} value={a.key}>{a.label}</option>)}
                </select>
                <select required value={f.question_key} onChange={(e) => set({ question_key: e.target.value })} aria-label={t('Question')} style={{ maxWidth: '100%' }}>
                  <option value="">{t('Question…')}</option>
                  {questions.map((q, i) => <option key={q.key} value={q.key}>{`${i + 1}. ${qText(q)}`}</option>)}
                </select>
              </div>
              <div className="row" style={{ gap: 16 }}>
                <span className="row" style={{ gap: 6 }}>
                  <span className="small muted">{t('Language of the question')}</span>
                  <span className="seg" role="group" aria-label={t('Language of the question')}>
                    {['ar', 'en'].map((k) => <button type="button" key={k} aria-pressed={f.lang === k} onClick={() => set({ lang: k })}>{t(LANG_NAME[k])}</button>)}
                  </span>
                </span>
                {!browser && (
                  <span className="row" style={{ gap: 6 }}>
                    <span className="small muted">{t('Asked')}</span>
                    <span className="seg" role="group" aria-label={t('Where it was asked from')}>
                      {['LY', 'other'].map((k) => <button type="button" key={k} aria-pressed={f.asked_in === k} onClick={() => set({ asked_in: k })}>{code(ASKED_IN, k, { country })}</button>)}
                    </span>
                  </span>)}
              </div>
              {browser && <p className="small muted" style={{ margin: 0 }}>{t('A browser session is recorded as asked from London, in a signed-in account. Its results are shown apart from the team’s and from the automatic audit.')}</p>}
              <label>{t('Source links, one per line')}
                <textarea dir="auto" rows={5} value={f.links} disabled={f.no_sources} onChange={(e) => set({ links: e.target.value })}
                  placeholder={t('https://… (one link per line)')} />
              </label>
              <label className="row small" style={{ display: 'flex' }}>
                <input type="checkbox" checked={f.no_sources} onChange={(e) => set({ no_sources: e.target.checked })} />{t('No sources shown')}
              </label>
              {!f.no_sources && f.links.trim() !== '' && (
                <div className="small" role="status">
                  {found.length === 0 ? <span className="err">{t('No web links found. Each link must start with http:// or https://.')}</span>
                    : <span className="muted">{tn(found.length, '{n} link found', '{n} links found')}</span>}
                  {tooMany && <div className="err">{t('At most {max} links per entry.', { max: maxLinks })}</div>}
                  {pastedText && <div className="muted">{t('Only the links are sent. The rest of the text is left out.')}</div>}
                </div>)}
              {full && <p className="small err" style={{ margin: 0 }}>{t('The weekly limit of {limit} entries is reached.', { limit })}</p>}
              <div className="row">
                <button className="btn primary" disabled={!ready}>{t('Save entry')}</button>
                {msg && <span className={msg.ok ? 'small' : 'small err'} role="status">{msg.text}</span>}
              </div>
            </form>)}

          {(!ro || mine.length > 0) && <h3>{t('Your entries this week')}</h3>}
          {mine.length === 0 ? (!ro && <p className="small muted">{t('No entries yet this week.')}</p>) : (
            <ul className="list small">{mine.map((e) => {
              const q = qByKey[e.question_key]
              return (
                <li key={e.id} className="row" style={{ justifyContent: 'space-between', flexWrap: 'nowrap' }}>
                  <div style={{ minWidth: 0 }}>
                    <b>{q ? `${q.n}.` : ''}</b> <span dir="auto">{q ? qText(q) : e.question_key}</span>
                    <div className="muted">
                      {e.app_label || appLabel(e.app)} · {code(LANG_NAME, e.lang)}{e.asked_in && <> · {code(ASKED_IN, e.asked_in, { country })}</>}
                      {' · '}{e.no_sources ? t('no sources shown') : t('Links: {links}, matched: {matched}', { links: nLinks(e), matched: e.matched ?? 0 })}
                      {e.created_at && <> · {fmtDate(e.created_at)}</>}
                      {e.origin === 'browser' && <> <span className="pill">{t('browser session')}</span></>}
                    </div>
                    {Array.isArray(e.links) && e.links.length > 0 && (
                      <details><summary className="muted" style={{ cursor: 'pointer' }}>{t('Show the links')}</summary>
                        <ul style={{ margin: '4px 0', paddingInlineStart: 18 }}>{e.links.map((l, i) => {
                          const u = typeof l === 'string' ? l : l?.url
                          return <li key={i}><span dir="auto" style={{ wordBreak: 'break-all' }}>{u}</span></li>
                        })}</ul></details>)}
                  </div>
                  <button className="btn small ghost" onClick={() => remove(e.id)}>{t('Delete')}</button>
                </li>)
            })}</ul>)}
        </>)}
    </section>
  )
}
