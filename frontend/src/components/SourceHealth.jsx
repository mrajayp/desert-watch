import { useEffect, useState } from 'react'
import { api } from '../api'

const STATUS = { ok: '●', partial: '◐', error: '✕', awaiting_key: '○', never_run: '○', running: '…' }

export default function SourceHealth({ compact = false }) {
  const [rows, setRows] = useState([])
  useEffect(() => { api('/api/sources/health').then(setRows).catch(() => {}) }, [])
  if (!rows.length) return null
  const bad = rows.filter((r) => r.status === 'error' || (r.stale && r.status !== 'awaiting_key'))
  const waiting = rows.filter((r) => r.status === 'awaiting_key')
  if (compact) {
    return (
      <div className={`banner ${bad.length ? '' : 'info'}`} role="status">
        <div className="row small">
          <b>Sources</b>
          {rows.map((r) => (
            <span key={r.key} className="pill" title={`${r.label}: ${r.status}${r.last_ok ? ` · last ok ${r.last_ok.slice(0, 16)}` : ''}${r.error ? `\n${r.error}` : ''}`}>
              <span aria-hidden="true" style={{ color: r.status === 'ok' && !r.stale ? 'var(--good)' : r.status === 'error' || r.stale ? 'var(--critical)' : 'var(--muted)' }}>{STATUS[r.status] || '?'}</span>
              {r.label}{r.stale && r.status !== 'awaiting_key' && r.status !== 'never_run' ? ' (stale)' : ''}{r.status === 'awaiting_key' ? ' (needs key)' : ''}
            </span>))}
        </div>
        <div className="small muted" style={{ marginTop: 4 }}>
          Coverage = what we can monitor. {waiting.length > 0 && `Event and humanitarian lenses switch on when their keys arrive (${waiting.map((w) => w.label).join(', ')}).`}
        </div>
      </div>
    )
  }
  return (
    <table className="data">
      <thead><tr><th>Source</th><th>Status</th><th>Last success</th><th className="num">Rows (last run)</th><th>Note</th></tr></thead>
      <tbody>{rows.map((r) => (
        <tr key={r.key}><td>{r.label}</td><td>{r.status}{r.stale && r.status !== 'awaiting_key' ? ' · stale' : ''}</td>
          <td className="mono">{r.last_ok?.slice(0, 16) || '–'}</td><td className="num">{r.rows}</td>
          <td className="small muted" style={{ maxWidth: 360, whiteSpace: 'pre-wrap' }}>{r.error?.split('\n')[0]}</td></tr>))}
      </tbody>
    </table>
  )
}
