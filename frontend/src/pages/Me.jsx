import { useState } from 'react'
import { api } from '../api'
import { useApp } from '../App'
import { ErrorBox } from '../components/Notices'
import { useMutation } from '../hooks/useMutation'
import { usePageTitle } from '../hooks/usePageTitle'
import { t } from '../i18n'

export default function Me() {
  const { me, setMe } = useApp()
  usePageTitle(t('Privacy'))
  const [confirm, setConfirm] = useState('')
  const [pw, setPw] = useState({ current: '', next: '' })
  const [pwMsg, setPwMsg] = useState(null)
  const [busy, setBusy] = useState(false)
  const word = t('delete') // the word to type before the account can be deleted, in the interface language
  const exportData = useMutation(async () => {
    const data = await api('/api/me/export')
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }))
    const a = document.createElement('a'); a.href = url; a.download = 'desert-watch-my-data.json'; a.click()
  })
  const del = useMutation(() => api('/api/me', { method: 'DELETE' }), { onSuccess: () => setMe(null) })
  // a new password ends every other session of the account (the server does that); this browser stays signed in
  const changePassword = async (e) => {
    e.preventDefault(); setBusy(true); setPwMsg(null)
    try {
      await api('/api/me/password', { method: 'POST', body: { current: pw.current, new: pw.next } })
      setPw({ current: '', next: '' }); setPwMsg({ ok: true, text: t('Password changed. Other devices were signed out.') })
    } catch (err) { setPwMsg({ ok: false, text: err.message }) } finally { setBusy(false) }
  }
  // ends every session, this one included, so the app goes back to the sign-in page
  const signOutEverywhere = async () => { try { await api('/api/auth/logout-all', { method: 'POST' }) } catch { /* the sessions are gone either way */ } finally { setMe(null) } }
  return (
    <main className="page" style={{ maxWidth: 760 }}>
      <section className="card">
        <h2>{t('Privacy & your data')}</h2>
        <p>{t('Signed in as')} <b dir="auto">{me.display_name}</b> (<bdi>{me.email}</bdi>).</p>
        <h3>{t('Security')}</h3>
        <form className="form" onSubmit={changePassword}>
          <p className="small">{t('Changing the password signs out every other device.')}</p>
          <div className="row">
            <input type="password" autoComplete="current-password" required placeholder={t('Current password')} aria-label={t('Current password')} value={pw.current} onChange={(e) => setPw({ ...pw, current: e.target.value })} />
            <input type="password" autoComplete="new-password" required minLength={10} placeholder={t('New password (10+ characters)')} aria-label={t('New password (10+ characters)')} value={pw.next} onChange={(e) => setPw({ ...pw, next: e.target.value })} />
            <button className="btn" disabled={busy || !pw.current || pw.next.length < 10}>{t('Change password')}</button>
          </div>
          {pwMsg && <p className={pwMsg.ok ? 'small' : 'err'}>{pwMsg.text}</p>}
        </form>
        <p className="small">{t('Ends every session of this account, on every device and browser, including this one.')}</p>
        <button className="btn" onClick={signOutEverywhere}>{t('Sign out everywhere')}</button>
        <h3>{t('What is recorded')}</h3>
        <p className="small">{t('Your votes, comments, corrections, assessments and added articles, plus the gaps and articles you view, click and spend time on and the filters you use. Stored under a pseudonymous ID; raw activity logs are deleted after 12 months; never shared with third-party analytics.')}</p>
        <h3>{t('Export')}</h3>
        <button className="btn" disabled={exportData.busy} onClick={() => exportData.run()}>{t('Download everything stored about me (JSON)')}</button>
        {exportData.error && <ErrorBox error={exportData.error} compact />}
        <h3>{t('Delete account')}</h3>
        <p className="small">{t('Deletes your account, behaviour log and comment text. Your votes and labels stay only in anonymised form.')}</p>
        <div className="row"><input type="text" dir="auto" placeholder={t('Type "delete" to confirm')} value={confirm} onChange={(e) => setConfirm(e.target.value)} />
          <button className="btn" disabled={confirm !== word || del.busy} onClick={() => del.run()}>{t('Delete my account')}</button></div>
        {del.error && <ErrorBox error={del.error} compact />}
      </section>
    </main>
  )
}
