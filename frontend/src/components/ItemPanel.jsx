import { useEffect, useState } from 'react'
import { api, dwell } from '../api'
import { useApp } from '../App'
import { useApi } from '../hooks/useApi'
import { useMutation } from '../hooks/useMutation'
import { usePageTitle } from '../hooks/usePageTitle'
import { N_, fmtDate, isAr, pick, t } from '../i18n'
import { articlePath } from '../routes'
import { CorrectionForm } from './ArticleRow'
import Comments from './Comments'
import CopyLink from './CopyLink'
import Dialog from './Dialog'
import { ErrorBox, Loading } from './Notices'
import { ThemePills } from './ThemeLabels'

const DIMS = [
  ['accuracy', N_('Accuracy'), [N_('Doubtful'), N_('Mostly sound'), N_('Solid')]],
  ['depth', N_('Depth'), [N_('Surface / rewrite'), N_('Some reporting'), N_('In-depth')]],
  ['local_sourcing', N_('Local voices'), [N_('None'), N_('Some'), N_('Central')]],
]
// a publication day (YYYY-MM-DD): as is in English, with Libyan month names in Arabic
const day = (d) => (isAr() ? fmtDate(d) : d)

// One article: /articles/:id. Rate it, correct its topics and places, discuss it.
export default function ItemPanel({ id }) {
  const { meta, closePanel, openOutlet, can } = useApp()
  const q = useApi(`/api/items/${id}`)
  const it = q.data
  const [form, setForm] = useState({ accuracy: 0, depth: 0, local_sourcing: 0, note: '' })
  const [saved, setSaved] = useState(false)
  const [fixing, setFixing] = useState(false)
  useEffect(() => { if (it?.assessments?.mine) setForm({ ...it.assessments.mine, note: it.assessments.mine.note || '' }) }, [it])
  useEffect(() => dwell('item', id), [id])
  usePageTitle(it?.title || t('Article'))
  const save = useMutation(() => api(`/api/items/${id}/assessment`, { method: 'POST', body: { ...form, note: form.note || null } }),
    { onSuccess: () => { setSaved(true); q.retry() } })
  const regions = new Map(meta.regions.map((r) => [r.id, r]))
  const a = it?.assessments
  return (
    <Dialog title={<span dir="auto">{it?.title || t('Article')}</span>} onClose={closePanel} actions={<CopyLink path={articlePath(id)} objectType="item" objectKey={id} />}>
      {!it && q.error && <ErrorBox error={q.error} onRetry={q.retry} />}
      {!it && !q.error && <Loading />}
      {it && (
        <>
          {q.error && <ErrorBox error={q.error} onRetry={q.retry} compact />}
          <p className="small muted">{day(it.published_at.slice(0, 10))} · <button className="btn small ghost" style={{ padding: 0 }} onClick={() => it.outlet && openOutlet(it.outlet.id)}>{it.outlet?.name}</button> · <a href={it.url} target="_blank" rel="noreferrer noopener">{t('open article ↗')}</a></p>
          {it.snippet && <p dir="auto">{it.snippet}</p>}
          <h3>{t('Topics and places')}</h3>
          <div className="row small">
            <ThemePills item={it} />
            {(it.region_ids || []).map((r) => <span key={r} className="pill">📍 {pick(regions.get(r), 'name')}</span>)}
            {!it.theme_ids?.length && !it.region_ids?.length && <span className="muted">{t('none yet')}</span>}
            {can && <button className="btn small ghost" aria-expanded={fixing} onClick={() => setFixing(!fixing)} title={t('Correct topic or place')}>{t('Correct')}</button>}
          </div>
          {fixing && can && <CorrectionForm item={it} onChanged={(r) => q.setData((d) => ({ ...d, ...r }))} />}
          {can && (
            <>
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
                <button className="btn primary" disabled={save.busy || !form.accuracy || !form.depth || !form.local_sourcing} onClick={() => save.run()}>{t('Save assessment')}</button>
                {saved && <span className="small muted">{t('Saved')}</span>}
              </div>
              {save.error && <ErrorBox error={save.error} compact />}
            </>)}
          <p className="small muted">{t('Team average ({n}): accuracy {accuracy}, depth {depth}, local voices {local} (scale 1–3). Feeds each outlet’s quality score.', { n: a.count, accuracy: a.accuracy ?? '–', depth: a.depth ?? '–', local: a.local_sourcing ?? '–' })}</p>
          <h3>{t('Discussion')}</h3>
          <Comments objectType="item" objectKey={String(id)} />
        </>)}
    </Dialog>
  )
}
