import { fmt, sourceLabel } from '../charts/scales'
import { t } from '../i18n'

// "All · Google Alerts 34 · Outlet RSS 12 …" — one toggle per source present, with its count.
export default function SourceFilter({ counts, value, onChange }) {
  const entries = Object.entries(counts || {}).sort((a, b) => b[1] - a[1])
  if (entries.length < 2 && !value) return null
  const total = entries.reduce((n, [, c]) => n + c, 0)
  return (
    <div className="chips" role="group" aria-label={t('Filter by source')} style={{ margin: '4px 0 8px' }}>
      <button className="chip" aria-pressed={!value} onClick={() => onChange('')}>{t('All {n}', { n: fmt(total) })}</button>
      {entries.map(([k, c]) => (
        <button key={k} className="chip" aria-pressed={value === k} onClick={() => onChange(value === k ? '' : k)}>
          {sourceLabel(k)} {fmt(c)}</button>))}
    </div>
  )
}
