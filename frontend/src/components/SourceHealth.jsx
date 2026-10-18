import { Link } from 'react-router-dom'
import { useApp } from '../App'
import { useApi } from '../hooks/useApi'
import { fmtAgo, fmtDateTime, t, tn } from '../i18n'
import { ErrorBox } from './Notices'

const N_ = (s) => s // marks English for the catalogue; translated with t() when shown
// run statuses from the API are codes, shown as words
const STATUS_TEXT = { ok: N_('ok'), partial: N_('partial'), error: N_('error'), awaiting_key: N_('awaiting a key'), not_built: N_('not built yet'), never_run: N_('never run'), running: N_('running') }
const statusText = (s) => (STATUS_TEXT[s] ? t(STATUS_TEXT[s]) : s)
// not faults: a source waiting for its key, or one whose key is set but whose collector is not written yet
const WAITING = new Set(['awaiting_key', 'not_built'])

// compact: one line at the foot of the This week and Map pages: "Data updated 12 minutes ago · 2 sources
// stale · Help" (admins get a link to Admin instead). Otherwise the full table, on the Admin page.
export default function SourceHealth({ compact = false }) {
  const { me } = useApp()
  const q = useApi('/api/sources/health')
  const rows = q.data || []
  const bad = rows.filter((r) => r.status === 'error' || (r.stale && !WAITING.has(r.status) && r.status !== 'never_run'))
  if (compact) {
    if (!rows.length) return null
    const admin = me.role === 'admin'
    // the newest successful run of any source: when the data last changed (ISO stamps sort as text)
    const latest = rows.map((r) => r.last_ok).filter(Boolean).sort().pop()
    const parts = []
    if (latest) parts.push(t('Data updated {ago}', { ago: fmtAgo(latest) }))
    if (bad.length) parts.push(tn(bad.length, '{n} source stale', '{n} sources stale'))
    else if (admin) parts.push(t('All sources up to date'))
    if (!parts.length) return null
    return (
      <p className="small muted source-line" role="status">
        {parts.join(' · ')} · {admin ? <Link to="/admin">{t('Admin')}</Link> : <Link to="/help#updates">{t('Help')}</Link>}
      </p>
    )
  }
  if (!rows.length && q.error) return <ErrorBox error={q.error} onRetry={q.retry} compact />
  return (
    <table className="data">
      <thead><tr><th>{t('Source')}</th><th>{t('Status')}</th><th>{t('Last success')}</th><th className="num">{t('Rows (last run)')}</th><th>{t('Note')}</th></tr></thead>
      <tbody>{rows.map((r) => (
        <tr key={r.key}><td>{r.label}</td><td>{statusText(r.status)}{r.stale && !WAITING.has(r.status) ? ` · ${t('stale')}` : ''}</td>
          <td className="small">{r.last_ok ? fmtDateTime(r.last_ok) : '–'}</td><td className="num">{r.rows}</td>
          <td className="small muted" style={{ maxWidth: 360, whiteSpace: 'pre-wrap' }}>{r.error?.split('\n')[0]}</td></tr>))}
      </tbody>
    </table>
  )
}
