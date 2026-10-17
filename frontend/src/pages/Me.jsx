import { useState } from 'react'
import { api } from '../api'
import { useApp } from '../App'
import { t } from '../i18n'

export default function Me() {
  const { me, setMe } = useApp()
  const [confirm, setConfirm] = useState('')
  const word = t('delete') // the word to type before the account can be deleted, in the interface language
  const exportData = async () => {
    const data = await api('/api/me/export')
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }))
    const a = document.createElement('a'); a.href = url; a.download = 'desert-watch-my-data.json'; a.click()
  }
  const del = async () => { await api('/api/me', { method: 'DELETE' }); setMe(null) }
  return (
    <main className="page" style={{ maxWidth: 760 }}>
      <section className="card">
        <h2>{t('Privacy & your data')}</h2>
        <p>{t('Signed in as')} <b dir="auto">{me.display_name}</b> (<bdi>{me.email}</bdi>).</p>
        <h3>{t('What is recorded')}</h3>
        <p className="small">{t('Your votes, comments, corrections, assessments and added articles, plus the gaps and articles you view, click and spend time on and the filters you use. Stored under a pseudonymous ID; raw activity logs are deleted after 12 months; never shared with third-party analytics.')}</p>
        <h3>{t('Export')}</h3>
        <button className="btn" onClick={exportData}>{t('Download everything stored about me (JSON)')}</button>
        <h3>{t('Delete account')}</h3>
        <p className="small">{t('Deletes your account, behaviour log and comment text. Your votes and labels stay only in anonymised form.')}</p>
        <div className="row"><input type="text" dir="auto" placeholder={t('Type "delete" to confirm')} value={confirm} onChange={(e) => setConfirm(e.target.value)} />
          <button className="btn" disabled={confirm !== word} onClick={del}>{t('Delete my account')}</button></div>
      </section>
    </main>
  )
}
