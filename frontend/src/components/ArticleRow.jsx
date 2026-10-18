import { useEffect, useState } from 'react'
import { api, track } from '../api'
import { useApp } from '../App'
import { DIMENSIONS, sourceLabel } from '../charts/scales'
import { useMutation } from '../hooks/useMutation'
import EngagementChip from './EngagementChip'
import { ErrorBox } from './Notices'
import { LabelForm, ThemePills } from './ThemeLabels'
import { N_, fmtDate, isAr, pick, t } from '../i18n'

// a publication day (YYYY-MM-DD): as is in English, with Libyan month names in Arabic
const day = (d) => (isAr() ? fmtDate(d) : d)

// article language: the code in English (AR, EN), the name in Arabic
const LANG = { ar: N_('Arabic'), en: N_('English'), und: N_('Language not detected') }
const langName = (l) => (isAr() ? t(LANG[l] || l || '') : (l || '').toUpperCase())

// a list with one row swapped for the row the server sent back after a correction
export const replaceItem = (items, r) => (items || []).map((x) => (x.id === r.id ? { ...x, ...r } : x))

// Topics and places of one article, each toggle one POST /correction (a training label). The row
// shown is the one the server sends back, so no list has to reload. Used on the row and on /articles/:id.
export function CorrectionForm({ item, onChanged }) {
  const { meta } = useApp()
  const regions = new Map(meta.regions.map((r) => [r.id, r]))
  const country = pick(meta.country, 'name')
  const correct = useMutation((body) => api(`/api/items/${item.id}/correction`, { method: 'POST', body }), { onSuccess: (r) => onChanged?.(r) })
  return (
    <div className="card" style={{ marginTop: 6, padding: 10 }}>
      <div className="small"><b>{t('Topics')}</b> {t('— toggle what this article is really about:')}</div>
      <div className="chips" style={{ margin: '4px 0 8px' }}>
        {meta.themes.map((th) => {
          const on = item.theme_ids.includes(th.id)
          return <button key={th.id} className="chip" aria-pressed={on} disabled={correct.busy} onClick={() => correct.run({ theme_id: th.id, theme_relevant: !on })}>{pick(th, 'name')}</button>
        })}
      </div>
      <div className="small"><b>{t('Places')}</b> {t('— add or remove districts:')}</div>
      <div className="row" style={{ margin: '4px 0 8px' }}>
        {item.region_ids.map((r) => <button key={r} className="chip" aria-pressed disabled={correct.busy} onClick={() => correct.run({ region_id: r, region_relevant: false })}>{pick(regions.get(r), 'name')} ✕</button>)}
        <select defaultValue="" disabled={correct.busy} onChange={(e) => e.target.value && correct.run({ region_id: +e.target.value, region_relevant: true })} aria-label={t('Add place')}>
          <option value="">{t('+ add place…')}</option>
          {meta.regions.filter((r) => r.level !== 'national').map((r) => <option key={r.id} value={r.id}>{r.level === 'macro' ? '▸ ' : ''}{pick(r, 'name')}</option>)}
        </select>
      </div>
      <button className="btn small" disabled={correct.busy} onClick={() => correct.run({ item_relevant: false })}>{t('Not about {country} / junk', { country })}</button>
      {correct.error && <ErrorBox error={correct.error} compact />}
    </div>
  )
}

// One article with inline corrections. Every correction is a training label.
export default function ArticleRow({ item: given, onChanged, context = {} }) {
  const { meta, openItem, openOutlet, can } = useApp()
  const [open, setOpen] = useState(null)  // 'fix' | 'label'
  const [row, setRow] = useState(given)   // the row as the server last sent it back
  const [note, setNote] = useState(null)  // 'saved' | 'off'
  useEffect(() => { setRow(given) }, [given])
  useEffect(() => { setNote(null) }, [given.id])
  const item = row
  const regions = new Map(meta.regions.map((r) => [r.id, r]))
  const changed = (r) => { setRow({ ...item, ...r }); onChanged?.({ ...item, ...r }) }
  const scope = item.outlet?.categories?.scope
  const country = pick(meta.country, 'name')
  return (
    <li>
      <div className="row" style={{ alignItems: 'flex-start', flexWrap: 'nowrap' }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <a href={item.url} target="_blank" rel="noreferrer noopener" dir="auto" onClick={() => track('click', 'item', item.id, { ...context, out: true })}>{item.title}</a>
          <div className="small muted">
            {day(item.published_at.slice(0, 10))} · <button className="btn small ghost" style={{ padding: 0 }} onClick={() => item.outlet && openOutlet(item.outlet.id)}>{item.outlet?.name || '—'}</button>
            {scope && ` · ${t(DIMENSIONS.scope.values[scope] || scope)}`} · {langName(item.lang)} · {t('via {source}', { source: t(sourceLabel(item.source)) })}{item.user_added && ` · ${t('added by team')}`}
            <EngagementChip e={item.engagement} />
          </div>
          <div className="row small" style={{ marginTop: 3 }}>
            <ThemePills item={item} />
            {item.region_ids.map((r) => <span key={r} className="pill">📍 {pick(regions.get(r), 'name')}</span>)}
            {can && <button className="btn small ghost" style={{ padding: '0 4px' }} aria-expanded={open === 'label'}
              onClick={() => setOpen(open === 'label' ? null : 'label')}>{t('Label this')}</button>}
            {note && <span className="muted">{note === 'off' ? t('Saved: not about {country}', { country }) : t('Saved')}</span>}
          </div>
        </div>
        <div className="row" style={{ flexWrap: 'nowrap' }}>
          {can ? (
            <>
              <button className="btn small" onClick={() => openItem(item.id, context)}>{t('Assess')}</button>
              <button className="btn small ghost" aria-expanded={open === 'fix'} onClick={() => setOpen(open === 'fix' ? null : 'fix')} title={t('Correct topic or place')}>{t('Fix')}</button>
            </>
          ) : <button className="btn small ghost" onClick={() => openItem(item.id, context)}>{t('Details')}</button>}
        </div>
      </div>
      {open === 'label' && (
        <div className="card" style={{ marginTop: 6, padding: 10 }}>
          <p className="small" style={{ margin: '0 0 8px' }}>{t('Tick every topic this article is about. Anything left unticked counts as a no.')}</p>
          <LabelForm item={item} onCancel={() => setOpen(null)}
            onSaved={(r, { off }) => { changed(r); setNote(off ? 'off' : 'saved'); setOpen(null) }} />
        </div>)}
      {open === 'fix' && <CorrectionForm item={item} onChanged={changed} />}
    </li>
  )
}
