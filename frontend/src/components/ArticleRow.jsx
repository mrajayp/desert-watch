import { useState } from 'react'
import { api, track } from '../api'
import { useApp } from '../App'
import { DIMENSIONS, sourceLabel } from '../charts/scales'
import EngagementChip from './EngagementChip'

// One article with inline corrections. Every correction is a training label.
export default function ArticleRow({ item, onChanged, context = {} }) {
  const { meta, openItem, openOutlet, lang } = useApp()
  const [open, setOpen] = useState(false)
  const themes = new Map(meta.themes.map((t) => [t.id, t]))
  const regions = new Map(meta.regions.map((r) => [r.id, r]))
  const correct = async (body) => { await api(`/api/items/${item.id}/correction`, { method: 'POST', body }); onChanged?.() }
  const scope = item.outlet?.categories?.scope
  return (
    <li>
      <div className="row" style={{ alignItems: 'flex-start', flexWrap: 'nowrap' }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <a href={item.url} target="_blank" rel="noreferrer noopener" dir="auto" onClick={() => track('click', 'item', item.id, { ...context, out: true })}>{item.title}</a>
          <div className="small muted">
            {item.published_at.slice(0, 10)} · <button className="btn small ghost" style={{ padding: 0 }} onClick={() => item.outlet && openOutlet(item.outlet.id)}>{item.outlet?.name || '—'}</button>
            {scope && ` · ${DIMENSIONS.scope.values[scope] || scope}`} · {item.lang?.toUpperCase()} · via {sourceLabel(item.source)}{item.user_added && ' · added by team'}
            <EngagementChip e={item.engagement} />
          </div>
          <div className="row small" style={{ marginTop: 3 }}>
            {item.theme_ids.map((t) => <span key={t} className="pill">{lang === 'ar' ? themes.get(t)?.name_ar : themes.get(t)?.name_en}</span>)}
            {item.region_ids.map((r) => <span key={r} className="pill">📍 {lang === 'ar' ? regions.get(r)?.name_ar : regions.get(r)?.name_en}</span>)}
          </div>
        </div>
        <div className="row" style={{ flexWrap: 'nowrap' }}>
          <button className="btn small" onClick={() => openItem(item.id)}>Assess</button>
          <button className="btn small ghost" aria-expanded={open} onClick={() => setOpen(!open)} title="Correct topic or place">Fix</button>
        </div>
      </div>
      {open && (
        <div className="card" style={{ marginTop: 6, padding: 10 }}>
          <div className="small"><b>Topics</b> — toggle what this article is really about:</div>
          <div className="chips" style={{ margin: '4px 0 8px' }}>
            {meta.themes.map((t) => {
              const on = item.theme_ids.includes(t.id)
              return <button key={t.id} className="chip" aria-pressed={on} onClick={() => correct({ theme_id: t.id, theme_relevant: !on })}>{t.name_en}</button>
            })}
          </div>
          <div className="small"><b>Places</b> — add or remove districts:</div>
          <div className="row" style={{ margin: '4px 0 8px' }}>
            {item.region_ids.map((r) => <button key={r} className="chip" aria-pressed onClick={() => correct({ region_id: r, region_relevant: false })}>{regions.get(r)?.name_en} ✕</button>)}
            <select defaultValue="" onChange={(e) => e.target.value && correct({ region_id: +e.target.value, region_relevant: true })} aria-label="Add place">
              <option value="">+ add place…</option>
              {meta.regions.filter((r) => r.level !== 'national').map((r) => <option key={r.id} value={r.id}>{r.level === 'macro' ? '▸ ' : ''}{r.name_en}</option>)}
            </select>
          </div>
          <button className="btn small" onClick={() => correct({ item_relevant: false })}>Not about {meta.country.name_en} / junk</button>
        </div>)}
    </li>
  )
}
