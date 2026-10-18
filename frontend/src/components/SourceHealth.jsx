import { useEffect, useState } from 'react'
import { api } from '../api'
import { getLang, t } from '../i18n'

const N_ = (s) => s // marks English for the catalogue; translated with t() when shown
const STATUS = { ok: '●', partial: '◐', error: '✕', awaiting_key: '○', not_built: '○', never_run: '○', running: '…' }
// run statuses from the API are codes; English shows the code itself
const STATUS_TEXT = { ok: N_('ok'), partial: N_('partial'), error: N_('error'), awaiting_key: N_('awaiting_key'), not_built: N_('not_built'), never_run: N_('never_run'), running: N_('running') }
const statusText = (s) => (STATUS_TEXT[s] ? t(STATUS_TEXT[s]) : s)
// not faults: a source waiting for its key, or one whose key is set but whose collector is not written yet
const WAITING = new Set(['awaiting_key', 'not_built'])
const suffix = (r) => (r.status === 'awaiting_key' ? ` (${t('needs key')})` : r.status === 'not_built' ? ` (${t('not built yet')})` : '')

export default function SourceHealth({ compact = false }) {
  const [rows, setRows] = useState([])
  useEffect(() => { api('/api/sources/health').then(setRows).catch(() => {}) }, [])
  if (!rows.length) return null
  const bad = rows.filter((r) => r.status === 'error' || (r.stale && !WAITING.has(r.status)))
  const waiting = rows.filter((r) => r.status === 'awaiting_key')
  if (compact) {
    return (
      <div className={`banner ${bad.length ? '' : 'info'}`} role="status">
        <div className="row small">
          <b>{t('Sources')}</b>
          {rows.map((r) => (
            <span key={r.key} className="pill" title={`${r.label}: ${statusText(r.status)}${r.last_ok ? ` · ${t('last ok {time}', { time: r.last_ok.slice(0, 16) })}` : ''}${r.error ? `\n${r.error}` : ''}`}>
              <span aria-hidden="true" style={{ color: r.status === 'ok' && !r.stale ? 'var(--good)' : r.status === 'error' || r.stale ? 'var(--critical)' : 'var(--muted)' }}>{STATUS[r.status] || '?'}</span>
              {r.label}{r.stale && !WAITING.has(r.status) && r.status !== 'never_run' ? ` (${t('stale')})` : ''}{suffix(r)}
            </span>))}
        </div>
        <div className="small muted" style={{ marginTop: 4 }}>
          {t('Coverage = what we can monitor.')} {waiting.length > 0 && t('These start when their keys arrive: {list}.', { list: waiting.map((w) => w.label).join(getLang() === 'ar' ? '، ' : ', ') })}
        </div>
      </div>
    )
  }
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
