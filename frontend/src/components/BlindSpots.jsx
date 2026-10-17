// Facebook blind-spot register: pages we only see through the posts Google News indexes, with reach
// from an external scrape (Oct 2023 - Aug 2024) and its labels as published. Makes "monitored coverage only" concrete.
import { useEffect, useState } from 'react'
import { api } from '../api'
import { useApp } from '../App'
import { fmt } from '../charts/scales'
import { isAr, t } from '../i18n'

const N_ = (s) => s // marks English for the catalogue; translated with t() when shown

// page kinds in the scrape register (a code from the API, shown as it is in English)
const KIND = { media: N_('media'), official: N_('official') }

export default function BlindSpots({ compact = false }) {
  const { openOutlet } = useApp()
  const [rows, setRows] = useState(null)
  const [kind, setKind] = useState('media')
  useEffect(() => { api('/api/outlets/blind-spots').then(setRows).catch(() => setRows([])) }, [])
  if (!rows || !rows.length) return null
  const shown = rows.filter((r) => kind === 'all' || r.kind === kind)
  const src = rows[0]
  if (compact) {
    const top = rows.filter((r) => r.kind === 'media').slice(0, 5)
    return (
      <p className="small muted">{t('Facebook-first outlets with large audiences may cover this ({names}…).', { names: top.map((r) => r.name).join(isAr() ? '، ' : ', ') })}
        {' '}{t('We only see the posts of theirs that Google News indexes. See Outlets → Facebook blind spots.')}</p>)
  }
  return (
    <section className="card" style={{ marginTop: 16 }}>
      <div className="card-head">
        <div><h2>{t('Facebook blind spots ({n})', { n: rows.length })}</h2>
          <p className="sub">{t('Facebook pages we only see in part. We collect the posts Google News indexes for them, which is a small sample of what they publish. Reach is from {source} ({from} to {to}).', { source: src.source ?? '', from: src.period?.from ?? '', to: src.period?.to ?? '' })}
            {' '}{t('Labels are shown exactly as published in that dataset and are disputed; they are not used in any filter or flag.')}</p></div>
        <span className="seg">{[['media', t('Media')], ['official', t('Official')], ['all', t('All')]].map(([k, l]) =>
          <button key={k} aria-pressed={kind === k} onClick={() => setKind(k)}>{l}</button>)}</span>
      </div>
      <div className="scroll" style={{ maxHeight: 420 }}>
        <table className="data">
          <thead><tr><th>{t('Page')}</th><th>{t('Kind')}</th><th className="num">{t('Posts')}</th><th className="num">{t('Interactions')}</th><th className="num">{t('Comments')}</th><th>{t('Label in the scrape')}</th><th /></tr></thead>
          <tbody>{shown.map((r) => (
            <tr key={r.id}>
              <td><b dir="auto">{r.name}</b>{r.link && <> <a className="small" href={r.link} target="_blank" rel="noreferrer noopener">{t('post')} ↗</a></>}</td>
              <td className="small">{KIND[r.kind] ? t(KIND[r.kind]) : r.kind}</td>
              <td className="num">{fmt(r.posts)}</td><td className="num">{fmt(r.interactions)}</td><td className="num">{fmt(r.comments)}</td>
              <td className="small">{Object.keys(r.labels).length ? <>{[r.labels.scrape_source_type, r.labels.scrape_affiliation].filter(Boolean).join(' · ')} <span className="pill">{t('disputed')}</span></> : <span className="muted">–</span>}</td>
              <td><button className="btn small ghost" onClick={() => openOutlet(r.id)}>{t('Open')}</button></td>
            </tr>))}</tbody>
        </table>
      </div>
    </section>
  )
}
