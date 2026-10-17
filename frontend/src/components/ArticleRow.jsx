import { useEffect, useState } from 'react'
import { api, track } from '../api'
import { useApp } from '../App'
import { DIMENSIONS, sourceLabel } from '../charts/scales'
import EngagementChip from './EngagementChip'
import { LabelForm, ThemePills } from './ThemeLabels'
import { N_, fmtDate, isAr, pick, t } from '../i18n'

// a publication day (YYYY-MM-DD): as is in English, with Libyan month names in Arabic
const day = (d) => (isAr() ? fmtDate(d) : d)

// One article with inline corrections. Every correction is a training label.
// article language: the code in English (AR, EN), the name in Arabic
const LANG = { ar: N_('Arabic'), en: N_('English'), und: N_('Language not detected') }
const langName = (l) => (isAr() ? t(LANG[l] || l || '') : (l || '').toUpperCase())

export default function ArticleRow({ item: given, onChanged, context = {} }) {
  const { meta, me, openItem, openOutlet } = useApp()
  const [open, setOpen] = useState(null)  // 'fix' | 'label'
  const [saved, setSaved] = useState(null)  // the row as the labels endpoint returned it
  useEffect(() => setSaved(null), [given])
  const item = saved || given
  const regions = new Map(meta.regions.map((r) => [r.id, r]))
  const correct = async (body) => { await api(`/api/items/${item.id}/correction`, { method: 'POST', body }); onChanged?.() }
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
            {me.role !== 'viewer' && <button className="btn small ghost" style={{ padding: '0 4px' }} aria-expanded={open === 'label'}
              onClick={() => setOpen(open === 'label' ? null : 'label')}>{t('Label this')}</button>}
            {saved && <span className="muted">{saved.relevant === false ? t('Saved: not about {country}', { country }) : t('Saved')}</span>}
          </div>
        </div>
        <div className="row" style={{ flexWrap: 'nowrap' }}>
          <button className="btn small" onClick={() => openItem(item.id)}>{t('Assess')}</button>
          <button className="btn small ghost" aria-expanded={open === 'fix'} onClick={() => setOpen(open === 'fix' ? null : 'fix')} title={t('Correct topic or place')}>{t('Fix')}</button>
        </div>
      </div>
      {open === 'label' && (
        <div className="card" style={{ marginTop: 6, padding: 10 }}>
          <p className="small" style={{ margin: '0 0 8px' }}>{t('Tick every topic this article is about. Anything left unticked counts as a no.')}</p>
          <LabelForm item={item} onCancel={() => setOpen(null)}
            onSaved={(r, { off }) => { setSaved({ ...r, relevant: !off }); setOpen(null) }} />
        </div>)}
      {open === 'fix' && (
        <div className="card" style={{ marginTop: 6, padding: 10 }}>
          <div className="small"><b>{t('Topics')}</b> {t('— toggle what this article is really about:')}</div>
          <div className="chips" style={{ margin: '4px 0 8px' }}>
            {meta.themes.map((t) => {
              const on = item.theme_ids.includes(t.id)
              return <button key={t.id} className="chip" aria-pressed={on} onClick={() => correct({ theme_id: t.id, theme_relevant: !on })}>{pick(t, 'name')}</button>
            })}
          </div>
          <div className="small"><b>{t('Places')}</b> {t('— add or remove districts:')}</div>
          <div className="row" style={{ margin: '4px 0 8px' }}>
            {item.region_ids.map((r) => <button key={r} className="chip" aria-pressed onClick={() => correct({ region_id: r, region_relevant: false })}>{pick(regions.get(r), 'name')} ✕</button>)}
            <select defaultValue="" onChange={(e) => e.target.value && correct({ region_id: +e.target.value, region_relevant: true })} aria-label={t('Add place')}>
              <option value="">{t('+ add place…')}</option>
              {meta.regions.filter((r) => r.level !== 'national').map((r) => <option key={r.id} value={r.id}>{r.level === 'macro' ? '▸ ' : ''}{pick(r, 'name')}</option>)}
            </select>
          </div>
          <button className="btn small" onClick={() => correct({ item_relevant: false })}>{t('Not about {country} / junk', { country })}</button>
        </div>)}
    </li>
  )
}
