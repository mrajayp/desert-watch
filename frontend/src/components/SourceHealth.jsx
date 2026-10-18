import { Link } from 'react-router-dom'
import { useApp } from '../App'
import { useApi } from '../hooks/useApi'
import { t, tn } from '../i18n'
import { ErrorBox } from './Notices'

const N_ = (s) => s // marks English for the catalogue; translated with t() when shown
// run statuses from the API are codes; English shows the code itself
const STATUS_TEXT = { ok: N_('ok'), partial: N_('partial'), error: N_('error'), awaiting_key: N_('awaiting_key'), not_built: N_('not_built'), never_run: N_('never_run'), running: N_('running') }
const statusText = (s) => (STATUS_TEXT[s] ? t(STATUS_TEXT[s]) : s)
// not faults: a source waiting for its key, or one whose key is set but whose collector is not written yet
const WAITING = new Set(['awaiting_key', 'not_built'])

// compact: one line at the foot of the map page ("2 sources stale", with a link to Admin for admins).
// Otherwise the full table, on the Admin page.
export default function SourceHealth({ compact = false }) {
  const { me } = useApp()
  const q = useApi('/api/sources/health')
  const rows = q.data || []
  const bad = rows.filter((r) => r.status === 'error' || (r.stale && !WAITING.has(r.status) && r.status !== 'never_run'))
  if (compact) {
    if (!rows.length) return null
    const admin = me.role === 'admin'
    if (!bad.length && !admin) return null
    return (
      <p className="small muted source-line" role="status">
        {bad.length ? tn(bad.length, '{n} source stale', '{n} sources stale') : t('All sources up to date')}
        {admin && <> · <Link to="/admin">{t('Admin')}</Link></>}
      </p>
    )
  }
  if (!rows.length && q.error) return <ErrorBox error={q.error} onRetry={q.retry} compact />
  return (
    <table className="data">
      <thead><tr><th>{t('Source')}</th><th>{t('Status')}</th><th>{t('Last success')}</th><th className="num">{t('Rows (last run)')}</th><th>{t('Note')}</th></tr></thead>
      <tbody>{rows.map((r) => (
        <tr key={r.key}><td>{r.label}</td><td>{statusText(r.status)}{r.stale && !WAITING.has(r.status) ? ` · ${t('stale')}` : ''}</td>
          <td className="mono">{r.last_ok?.slice(0, 16) || '–'}</td><td className="num">{r.rows}</td>
          <td className="small muted" style={{ maxWidth: 360, whiteSpace: 'pre-wrap' }}>{r.error?.split('\n')[0]}</td></tr>))}
      </tbody>
    </table>
  )
}
