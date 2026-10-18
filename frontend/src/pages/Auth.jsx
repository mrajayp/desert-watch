import { useState } from 'react'
import { useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { usePageTitle } from '../hooks/usePageTitle'
import { t } from '../i18n'
import { safeNext } from '../routes'
import LangSwitch from '../components/LangSwitch'

function Brand() {
  return <div className="brand"><span className="brand-mark" aria-hidden="true" />Desert Watch</div>
}

// Sign in or request access. /login?next=/gaps/3/7 returns to that page after sign-in; any other
// path (a shared link opened while signed out) simply renders once the user is known.
export function Login({ onDone, lang, setLang }) {
  const [mode, setMode] = useState('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [org, setOrg] = useState('')
  const [note, setNote] = useState('')
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(null)
  const [sp] = useSearchParams()
  const loc = useLocation()
  const nav = useNavigate()
  usePageTitle(mode === 'login' ? t('Sign in') : t('Request access'))
  const submit = async (e) => {
    e.preventDefault()
    setErr(null); setBusy(true)
    try {
      if (mode === 'login') {
        const me = await api('/api/auth/login', { method: 'POST', body: { email, password } })
        if (loc.pathname === '/login') nav(safeNext(sp.get('next')), { replace: true })
        onDone(me)
      } else {
        const r = await api('/api/auth/signup', { method: 'POST', body: { email, password, display_name: name, organisation: org, note } })
        setDone(r.message); setPassword('')
      }
    } catch (ex) { setErr(ex.message) } finally { setBusy(false) }
  }
  return (
    <div className="center-page">
      <div className="card auth-card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}><Brand /><LangSwitch lang={lang} setLang={setLang} /></div>
        <p className="sub">{t('Find the stories nobody is covering in Libya: where need is high and monitored coverage is thin.')}</p>
        <div className="seg" role="tablist" style={{ marginBottom: 12 }}>
          <button type="button" role="tab" aria-selected={mode === 'login'} onClick={() => { setMode('login'); setDone(null); setErr(null) }}>{t('Sign in')}</button>
          <button type="button" role="tab" aria-selected={mode === 'signup'} onClick={() => { setMode('signup'); setErr(null) }}>{t('Request access')}</button>
        </div>
        {done ? (
          <div><p>{done}</p><p className="small muted">{t('You’ll be able to sign in once an admin approves your request.')}</p>
            <button className="btn" onClick={() => { setMode('login'); setDone(null) }}>{t('Back to sign in')}</button></div>
        ) : (
          <form className="form" onSubmit={submit}>
            {mode === 'signup' && <label>{t('Your name')}<input type="text" dir="auto" value={name} onChange={(e) => setName(e.target.value)} required maxLength={100} /></label>}
            <label>{t('Email')}<input type="email" dir="auto" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
            <label>{t('Password')}{mode === 'signup' && ` ${t('(10+ characters)')}`}
              <input type="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} minLength={mode === 'signup' ? 10 : undefined}
                value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
            {mode === 'signup' && <>
              <label>{t('Organisation (optional)')}<input type="text" dir="auto" value={org} onChange={(e) => setOrg(e.target.value)} maxLength={200} /></label>
              <label>{t('Why do you want access? (optional)')}<textarea dir="auto" value={note} onChange={(e) => setNote(e.target.value)} maxLength={2000} /></label>
              <p className="small muted">{t('Requests are reviewed by an admin. Accounts start read-only; the admin sets your role.')}</p>
            </>}
            {err && <p className="err">{err}</p>}
            <button className="btn primary" disabled={busy}>{mode === 'login' ? t('Sign in') : t('Request access')}</button>
          </form>)}
      </div>
    </div>
  )
}

export function Invite({ onDone, lang, setLang }) {
  const { token } = useParams()
  const nav = useNavigate()
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState(null)
  usePageTitle(t('Create account'))
  const submit = async (e) => {
    e.preventDefault()
    try { const me = await api('/api/auth/accept-invite', { method: 'POST', body: { token, password, display_name: name } }); nav('/'); onDone(me) }
    catch (ex) { setErr(ex.message) }
  }
  return (
    <div className="center-page">
      <form className="card auth-card form" onSubmit={submit}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}><Brand /><LangSwitch lang={lang} setLang={setLang} /></div>
        <p className="sub">{t('You’ve been invited. Choose how your name appears to your team.')}</p>
        <label>{t('Display name')}<input type="text" dir="auto" value={name} onChange={(e) => setName(e.target.value)} required /></label>
        <label>{t('Password (10+ characters)')}<input type="password" autoComplete="new-password" minLength={10} value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
        {err && <p className="err">{err}</p>}
        <button className="btn primary">{t('Create account')}</button>
      </form>
    </div>
  )
}
