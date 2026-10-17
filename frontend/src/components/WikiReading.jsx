// The Libya pages people in Libya read on Wikipedia, day by day (/api/wiki-reading). Most days only
// a few pages clear Wikimedia's privacy threshold. Days when something happened stand out.
import { useEffect, useState } from 'react'
import { api, qs } from '../api'
import { fmt } from '../charts/scales'
import { fmtDate, t } from '../i18n.js'

const dayLabel = (d) => fmtDate(d, { weekday: 'short', day: 'numeric', month: 'short' })

export default function WikiReading({ days = 30 }) {
  const [data, setData] = useState(null)
  const [all, setAll] = useState(false)
  useEffect(() => { api('/api/wiki-reading' + qs({ days: all ? 365 : days })).then(setData).catch(() => setData({ days: [] })) }, [all, days])
  if (!data) return <div className="empty small">{t('Loading…')}</div>
  if (!data.days.length) return <div className="empty small">{t('No days collected yet.')}</div>
  const busiest = Math.max(...data.days.map((d) => d.pages.length))
  return (
    <>
      <ul className="list small" style={{ listStyle: 'none', padding: 0, margin: 0 }}>
        {data.days.map((d) => (
          <li key={d.day} style={{ display: 'flex', gap: 10, padding: '5px 0', borderTop: '1px solid var(--line)', alignItems: 'baseline' }}>
            <span className="muted" style={{ minWidth: 96, fontWeight: d.pages.length >= Math.max(4, busiest * 0.6) ? 700 : 400 }}>{dayLabel(d.day)}</span>
            <span style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {d.pages.length ? d.pages.map((p) => (
                <a key={p.project + p.title} className="pill" href={p.url || undefined} target="_blank" rel="noreferrer"
                  dir="auto" title={t('{project}, about {views} views from Libya that day', { project: p.project, views: fmt(p.views), n: p.views })}>
                  {p.title} <span className="muted">· {fmt(p.views)}</span></a>))
                : <span className="muted">{t('No Libya page above the threshold')}</span>}
            </span>
          </li>))}
      </ul>
      <div className="row" style={{ justifyContent: 'space-between', marginTop: 8 }}>
        <span className="small muted">{data.note}</span>
        <button type="button" className="linkish small" onClick={() => setAll(!all)}>{all ? t('Last 30 days') : t('The last year')}</button>
      </div>
    </>
  )
}
