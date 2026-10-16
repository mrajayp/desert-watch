import { useState } from 'react'
import { api } from '../api'
import { useApp } from '../App'

// Why each theme link exists, and the full theme-set label (POST /api/items/{id}/labels).
// item.theme_detail evidence: rule/query links {field: title|snippet|query, terms, query},
// model links {model, was}, a rule link the model turned off {veto}.

const words = (slug) => (slug || '').replace(/_/g, ' ')
const p2 = (x) => (x == null ? '' : Number(x).toFixed(2))

// "gnews:governance" -> search: governance, "theme:gender_violence:en" -> alert: gender violence
function queryText(q) {
  if (!q) return 'search'
  const [kind, slug] = q.split(':')
  return `${kind === 'theme' ? 'alert' : 'search'}: ${words(slug)}`
}

// {text, title}: a few words for the row, more for the hover
export function why(d) {
  const ev = d.evidence || {}
  const more = []
  let text
  if (d.method === 'user') text = 'you said so'
  else if (d.method === 'model') {
    text = `model ${p2(d.score ?? ev.model)}`
    if (ev.was) more.push(`first linked by ${ev.was === 'query' ? 'a search' : 'the word rules'}`)
  } else if (ev.field && ev.field !== 'query' && ev.terms?.length) {
    text = `${ev.field}: ${ev.terms.length === 1 ? ev.terms[0] : `${ev.terms.length} terms`}`
    more.push(`words in the ${ev.field}: ${ev.terms.join(', ')}`)
  } else if (d.method === 'query' || ev.field === 'query') text = queryText(ev.query)
  else text = 'rule'
  if (ev.query && d.method !== 'query') more.push(`also returned by ${queryText(ev.query)}`)
  if (d.score != null && d.method !== 'model') more.push(`model ${p2(d.score)}`)
  if (ev.veto != null) more.push(`the model said no (${p2(ev.veto)})`)
  return { text, title: [text, ...more].join('\n') }
}

const themeName = (t, lang) => (lang === 'ar' ? t.name_ar : t.name_en)

// The item's counted themes, each with why it is there
export function ThemePills({ item }) {
  const { meta, lang } = useApp()
  const themes = new Map(meta.themes.map((t) => [t.id, t]))
  const detail = new Map((item.theme_detail || []).map((d) => [d.theme_id, d]))
  return item.theme_ids.filter((t) => themes.has(t)).map((t) => {
    const w = detail.has(t) ? why(detail.get(t)) : null
    return (
      <span key={t} className="pill" title={w?.title}>
        {themeName(themes.get(t), lang)}{w && <span className="muted">{w.text}</span>}
      </span>)
  })
}

// Links kept but not counted: a search that the rules did not confirm, or a rule link the model vetoed
export function NotCounted({ item }) {
  const { meta, lang } = useApp()
  const themes = new Map(meta.themes.map((t) => [t.id, t]))
  const off = (item.theme_detail || []).filter((d) => !d.active && d.method !== 'user' && themes.has(d.theme_id))
  if (!off.length) return null
  return (
    <div className="small muted">
      Not counted: {off.map((d) => {
        const w = why(d)
        return <span key={d.theme_id} title={w.title}>{themeName(themes.get(d.theme_id), lang)} ({d.evidence?.veto != null ? `model said no ${p2(d.evidence.veto)}` : w.text})</span>
      }).reduce((a, x) => (a.length ? [...a, ' · ', x] : [x]), [])}
    </div>)
}

// One checkbox per active theme, ticked with the themes counted now. Unticked themes count as "no".
export function LabelForm({ item, onSaved, onSkip, onCancel, saveText = 'Save' }) {
  const { meta, lang } = useApp()
  const ids = new Set(meta.themes.map((t) => t.id))
  const [on, setOn] = useState(() => new Set(item.theme_ids.filter((t) => ids.has(t))))
  const [off, setOff] = useState(false)  // not about the country at all
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const flip = (id) => { const n = new Set(on); n.has(id) ? n.delete(id) : n.add(id); setOn(n) }
  const save = async () => {
    setBusy(true); setErr(null)
    try {
      const r = await api(`/api/items/${item.id}/labels`, { method: 'POST', body: { themes: off ? [] : [...on], libya: !off } })
      onSaved?.(r, { off })
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  const groups = [['Topics', meta.themes.filter((t) => t.group !== 'gender')], ['Gender', meta.themes.filter((t) => t.group === 'gender')]]
  return (
    <div>
      {groups.map(([label, ts]) => ts.length > 0 && (
        <fieldset key={label} disabled={off} style={{ border: 0, padding: 0, margin: '0 0 8px', opacity: off ? 0.5 : 1 }}>
          <legend className="small muted" style={{ padding: 0, marginBottom: 4 }}>{label}</legend>
          <div className="chips">{ts.map((t) => (
            <label key={t.id} className="chip row" style={{ gap: 5, flexWrap: 'nowrap' }}>
              <input type="checkbox" checked={on.has(t.id)} onChange={() => flip(t.id)} style={{ margin: 0 }} />
              {label === 'Gender' ? themeName(t, lang).replace(/^Gender:\s*/, '') : themeName(t, lang)}
            </label>))}</div>
        </fieldset>))}
      <label className="row small" style={{ gap: 6, margin: '2px 0 10px' }}>
        <input type="checkbox" checked={off} onChange={(e) => setOff(e.target.checked)} style={{ margin: 0 }} />
        Not about {meta.country.name_en}
      </label>
      <div className="row">
        <button className="btn small primary" disabled={busy} onClick={save}>{busy ? 'Saving…' : saveText}</button>
        {onSkip && <button className="btn small" disabled={busy} onClick={onSkip}>Skip</button>}
        {onCancel && <button className="btn small ghost" disabled={busy} onClick={onCancel}>Cancel</button>}
        {err && <span className="err">{err}</span>}
      </div>
    </div>)
}
