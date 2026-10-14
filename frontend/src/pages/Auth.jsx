import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'

function Brand() {
  return <div className="brand"><span className="brand-mark" aria-hidden="true" />Desert Watch</div>
}

export function Login({ onDone }) {
  const [mode, setMode] = useState('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [org, setOrg] = useState('')
  const [note, setNote] = useState('')
  const [err, setErr] = useState(null)
  const [done, setDone] = useState(null)
  const submit = async (e) => {
    e.preventDefault()
    setErr(null)
    try {
      if (mode === 'login') onDone(await api('/api/auth/login', { method: 'POST', body: { email, password } }))
      else {
        const r = await api('/api/auth/signup', { method: 'POST', body: { email, password, display_name: name, organisation: org, note } })
        setDone(r.message); setPassword('')
      }
    } catch (ex) { setErr(ex.message) }
  }
  return (
    <div className="center-page">
      <div className="card auth-card">
        <Brand />
        <p className="sub">Find the stories nobody is covering in Libya: where need is high and monitored coverage is thin.</p>
        <div className="seg" role="tablist" style={{ marginBottom: 12 }}>
          <button role="tab" aria-pressed={mode === 'login'} aria-selected={mode === 'login'} onClick={() => { setMode('login'); setDone(null); setErr(null) }}>Sign in</button>
          <button role="tab" aria-pressed={mode === 'signup'} aria-selected={mode === 'signup'} onClick={() => { setMode('signup'); setErr(null) }}>Request access</button>
        </div>
        {done ? (
          <div><p>{done}</p><p className="small muted">You’ll be able to sign in once an admin approves your request.</p>
            <button className="btn" onClick={() => { setMode('login'); setDone(null) }}>Back to sign in</button></div>
        ) : (
          <form className="form" onSubmit={submit}>
            {mode === 'signup' && <label>Your name<input type="text" value={name} onChange={(e) => setName(e.target.value)} required maxLength={100} /></label>}
            <label>Email<input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
            <label>Password{mode === 'signup' && ' (10+ characters)'}
              <input type="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} minLength={mode === 'signup' ? 10 : undefined}
                value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
            {mode === 'signup' && <>
              <label>Organisation (optional)<input type="text" value={org} onChange={(e) => setOrg(e.target.value)} maxLength={200} /></label>
              <label>Why do you want access? (optional)<textarea dir="auto" value={note} onChange={(e) => setNote(e.target.value)} maxLength={2000} /></label>
              <p className="small muted">Requests are reviewed by an admin. Accounts start read-only; the admin sets your role.</p>
            </>}
            {err && <p className="err">{err}</p>}
            <button className="btn primary">{mode === 'login' ? 'Sign in' : 'Request access'}</button>
          </form>)}
      </div>
    </div>
  )
}

export function Invite({ onDone }) {
  const { token } = useParams()
  const nav = useNavigate()
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState(null)
  const submit = async (e) => {
    e.preventDefault()
    try { const me = await api('/api/auth/accept-invite', { method: 'POST', body: { token, password, display_name: name } }); nav('/'); onDone(me) }
    catch (ex) { setErr(ex.message) }
  }
  return (
    <div className="center-page">
      <form className="card auth-card form" onSubmit={submit}>
        <Brand />
        <p className="sub">You’ve been invited. Choose how your name appears to your team.</p>
        <label>Display name<input type="text" value={name} onChange={(e) => setName(e.target.value)} required /></label>
        <label>Password (10+ characters)<input type="password" autoComplete="new-password" minLength={10} value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
        {err && <p className="err">{err}</p>}
        <button className="btn primary">Create account</button>
      </form>
    </div>
  )
}
