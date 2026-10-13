import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'

export function Login({ onDone }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState(null)
  const submit = async (e) => {
    e.preventDefault()
    try { onDone(await api('/api/auth/login', { method: 'POST', body: { email, password } })) } catch (ex) { setErr(ex.message) }
  }
  return (
    <div className="center-page">
      <form className="card auth-card form" onSubmit={submit}>
        <div className="brand"><span className="brand-mark" aria-hidden="true" />Desert Watch</div>
        <p className="sub">Find the stories nobody is covering. Invite only.</p>
        <label>Email<input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
        <label>Password<input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
        {err && <p className="err">{err}</p>}
        <button className="btn primary">Sign in</button>
      </form>
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
        <div className="brand"><span className="brand-mark" aria-hidden="true" />Desert Watch</div>
        <p className="sub">You’ve been invited. Choose how your name appears to your team.</p>
        <label>Display name<input type="text" value={name} onChange={(e) => setName(e.target.value)} required /></label>
        <label>Password (10+ characters)<input type="password" autoComplete="new-password" minLength={10} value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
        {err && <p className="err">{err}</p>}
        <button className="btn primary">Create account</button>
      </form>
    </div>
  )
}
