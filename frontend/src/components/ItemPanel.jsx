import { useEffect, useState } from 'react'
import { api, dwell } from '../api'
import { useApp } from '../App'
import Comments from './Comments'
import { N_, fmtDate, isAr, t } from '../i18n'

const DIMS = [
  ['accuracy', N_('Accuracy'), [N_('Doubtful'), N_('Mostly sound'), N_('Solid')]],
  ['depth', N_('Depth'), [N_('Surface / rewrite'), N_('Some reporting'), N_('In-depth')]],
  ['local_sourcing', N_('Local voices'), [N_('None'), N_('Some'), N_('Central')]],
]
// a publication day (YYYY-MM-DD): as is in English, with Libyan month names in Arabic
const day = (d) => (isAr() ? fmtDate(d) : d)

export default function ItemPanel({ id }) {
  const { closePanel, openOutlet } = useApp()
  const [it, setIt] = useState(null)
  const [form, setForm] = useState({ accuracy: 0, depth: 0, local_sourcing: 0, note: '' })
  const [saved, setSaved] = useState(false)
  const load = () => api(`/api/items/${id}`).then((x) => { setIt(x); if (x.assessments.mine) setForm({ ...x.assessments.mine, note: x.assessments.mine.note || '' }) })
  useEffect(() => { load() }, [id])
  useEffect(() => dwell('item', id), [id])
  if (!it) return <aside className="drawer"><div className="empty">{t('Loading…')}</div></aside>
  const save = async () => {
    await api(`/api/items/${id}/assessment`, { method: 'POST', body: { ...form, note: form.note || null } })
    setSaved(true); load()
  }
  const a = it.assessments
  return (
    <aside className="drawer" aria-label={t('Article')}>
      <div className="row" style={{ justifyContent: 'space-between', flexWrap: 'nowrap' }}>
        <h2 dir="auto" style={{ margin: 0, fontSize: 17 }}>{it.title}</h2>
        <button className="btn ghost" onClick={closePanel} aria-label={t('Close')}>✕</button>
      </div>
      <p className="small muted">{day(it.published_at.slice(0, 10))} · <button className="btn small ghost" style={{ padding: 0 }} onClick={() => it.outlet && openOutlet(it.outlet.id)}>{it.outlet?.name}</button> · <a href={it.url} target="_blank" rel="noreferrer noopener">{t('open article ↗')}</a></p>
      {it.snippet && <p dir="auto">{it.snippet}</p>}
      <h3>{t('Your assessment')}</h3>
      {DIMS.map(([k, label, opts]) => (
        <div key={k} className="row" style={{ marginBottom: 6 }}>
          <span style={{ width: 100 }}>{t(label)}</span>
          <span className="seg" role="radiogroup" aria-label={t(label)}>
            {opts.map((o, i) => <button key={o} role="radio" aria-checked={form[k] === i + 1} aria-pressed={form[k] === i + 1} onClick={() => { setSaved(false); setForm({ ...form, [k]: i + 1 }) }}>{t(o)}</button>)}
          </span>
        </div>))}
      <textarea dir="auto" placeholder={t('Optional note: what’s missing, what’s wrong, who should have been quoted…')} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
      <div className="row" style={{ marginTop: 6 }}>
        <button className="btn primary" disabled={!form.accuracy || !form.depth || !form.local_sourcing} onClick={save}>{t('Save assessment')}</button>
        {saved && <span className="small muted">{t('Saved')}</span>}
      </div>
      <p className="small muted">{t('Team average ({n}): accuracy {accuracy}, depth {depth}, local voices {local} (scale 1–3). Feeds each outlet’s quality score.', { n: a.count, accuracy: a.accuracy ?? '–', depth: a.depth ?? '–', local: a.local_sourcing ?? '–' })}</p>
      <h3>{t('Discussion')}</h3>
      <Comments objectType="item" objectKey={String(id)} />
    </aside>
  )
}
