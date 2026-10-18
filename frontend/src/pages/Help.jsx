import { useEffect } from 'react'
import { Link, Navigate, useLocation } from 'react-router-dom'
import { useApp } from '../App'
import { ErrorBox, Loading } from '../components/Notices'
import { useApi } from '../hooks/useApi'
import { usePageTitle } from '../hooks/usePageTitle'
import { t } from '../i18n'
import { Markdown } from './Digest'

// /help: the glossary and a short account of how the numbers are made, for every signed-in account
// (backend/app/content/help.md, Arabic twin help.ar.md). Links elsewhere point at /help#<term>: the
// headings carry {#id} anchors that are the same in both languages. /help/methods is the full method
// notes, admins only (GET /api/content/how_the_numbers_work).
export default function Help({ methods = false }) {
  const { me } = useApp()
  const loc = useLocation()
  usePageTitle(methods ? t('How the numbers work') : t('Help'))
  const q = useApi(methods ? '/api/content/how_the_numbers_work' : '/api/content/help')
  const md = q.data?.markdown
  // a link to /help#term lands on that term once the text is in
  useEffect(() => {
    if (!md || !loc.hash) return
    const el = document.getElementById(decodeURIComponent(loc.hash.slice(1)))
    if (el) el.scrollIntoView()
  }, [md, loc.hash])
  if (methods && me.role !== 'admin') return <Navigate to="/help" replace />
  return (
    <main className="page help" style={{ maxWidth: 820 }}>
      <section className="card">
        <h2>{methods ? t('How the numbers work') : t('Help')}</h2>
        {methods && <p className="sub">{t('How every figure in Desert Watch is worked out, and where it can mislead you.')}</p>}
        {!md && q.error && <ErrorBox error={q.error} onRetry={q.retry} />}
        {!md && !q.error && <Loading />}
        {md && <Markdown text={md.replace(/^# .*\n/, '')} />}
        {!methods && md && me.role === 'admin' && (
          <p className="small" style={{ marginTop: 18 }}><Link to="/help/methods">{t('Full method notes (admins)')}</Link></p>)}
      </section>
    </main>
  )
}
