import { useState } from 'react'
import { api } from '../api'
import { useApp } from '../App'
import { fmtNum, isAr, pick, t, tn } from '../i18n'

const N_ = (s) => s // marks English for the catalogue; translated with t() when read

// Why each theme link exists, and the full theme-set label (POST /api/items/{id}/labels).
// item.theme_detail evidence: rule/query links {field: title|snippet|query, terms, query},
// model links {model, was}, a rule link the model turned off {veto}.

const words = (slug) => (slug || '').replace(/_/g, ' ')
const p2 = (x) => (x == null ? '' : fmtNum(Number(x), { minimumFractionDigits: 2, maximumFractionDigits: 2, useGrouping: false }))
const sep = () => (isAr() ? '، ' : ', ')
// the field a rule matched, in the words the help page uses
const FIELD = { title: N_('title'), snippet: N_('summary') }

// "gnews:governance" -> search: governance, "theme:gender_violence:en" -> alert: gender violence
function queryText(q) {
  if (!q) return t('found by a search')
  const [kind, slug] = q.split(':')
  return kind === 'theme' ? t('alert: {what}', { what: words(slug) }) : t('search: {what}', { what: words(slug) })
}

// {text, title}: a few words for the row, more for the hover
export function why(d) {
  const ev = d.evidence || {}
  const more = []
  let text
  if (d.method === 'user') text = t('labelled by a person')
  else if (d.method === 'model') {
    text = t('model {score}', { score: p2(d.score ?? ev.model) })
    if (ev.was) more.push(ev.was === 'query' ? t('first linked by a search') : t('first linked by a word list'))
  } else if (ev.field && ev.field !== 'query' && ev.terms?.length) {
    const field = FIELD[ev.field] ? t(FIELD[ev.field]) : ev.field
    text = `${field}: ${ev.terms.length === 1 ? ev.terms[0] : tn(ev.terms.length, '{n} word', '{n} words')}`
    more.push(t('words in the {field}: {terms}', { field, terms: ev.terms.join(sep()) }))
  } else if (d.method === 'query' || ev.field === 'query') text = queryText(ev.query)
  else text = t('word list')
  if (ev.query && d.method !== 'query') more.push(t('also returned by {query}', { query: queryText(ev.query) }))
  if (d.score != null && d.method !== 'model') more.push(t('model {score}', { score: p2(d.score) }))
  if (ev.veto != null) more.push(t('the model said no ({score})', { score: p2(ev.veto) }))
  return { text, title: [text, ...more].join('\n') }
}

const themeName = (th) => pick(th, 'name')

// The item's counted themes, each with why it is there
export function ThemePills({ item }) {
  const { meta } = useApp()
  const themes = new Map(meta.themes.map((th) => [th.id, th]))
  const detail = new Map((item.theme_detail || []).map((d) => [d.theme_id, d]))
  return item.theme_ids.filter((id) => themes.has(id)).map((id) => {
    const w = detail.has(id) ? why(detail.get(id)) : null
    return (
      <span key={id} className="pill" title={w?.title}>
        {themeName(themes.get(id))}{w && <span className="muted">{w.text}</span>}
      </span>)
  })
}

// Links kept but not counted: a search that the rules did not confirm, or a rule link the model vetoed
export function NotCounted({ item }) {
  const { meta } = useApp()
  const themes = new Map(meta.themes.map((th) => [th.id, th]))
  const off = (item.theme_detail || []).filter((d) => !d.active && d.method !== 'user' && themes.has(d.theme_id))
  if (!off.length) return null
  return (
    <div className="small muted">
      {t('Not counted:')} {off.map((d) => {
        const w = why(d)
        return <span key={d.theme_id} title={w.title}>{themeName(themes.get(d.theme_id))} ({d.evidence?.veto != null ? t('model said no {score}', { score: p2(d.evidence.veto) }) : w.text})</span>
      }).reduce((a, x) => (a.length ? [...a, ' · ', x] : [x]), [])}
    </div>)
}

// One checkbox per active theme, ticked with the themes counted now. Unticked themes count as "no".
export function LabelForm({ item, onSaved, onSkip, onCancel, saveText = N_('Save') }) {
  const { meta } = useApp()
  const ids = new Set(meta.themes.map((th) => th.id))
  const [on, setOn] = useState(() => new Set(item.theme_ids.filter((id) => ids.has(id))))
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
  const groups = [[N_('Topics'), meta.themes.filter((th) => th.group !== 'gender')], [N_('Gender'), meta.themes.filter((th) => th.group === 'gender')]]
  return (
    <div>
      {groups.map(([label, ts]) => ts.length > 0 && (
        <fieldset key={label} disabled={off} style={{ border: 0, padding: 0, margin: '0 0 8px', opacity: off ? 0.5 : 1 }}>
          <legend className="small muted" style={{ padding: 0, marginBottom: 4 }}>{t(label)}</legend>
          <div className="chips">{ts.map((th) => (
            <label key={th.id} className="chip row" style={{ gap: 5, flexWrap: 'nowrap' }}>
              <input type="checkbox" checked={on.has(th.id)} onChange={() => flip(th.id)} style={{ margin: 0 }} />
              {label === 'Gender' ? themeName(th).replace(/^(Gender|النوع الاجتماعي):\s*/, '') : themeName(th)}
            </label>))}</div>
        </fieldset>))}
      <label className="row small" style={{ gap: 6, margin: '2px 0 10px' }}>
        <input type="checkbox" checked={off} onChange={(e) => setOff(e.target.checked)} style={{ margin: 0 }} />
        {t('Not about {country}', { country: pick(meta.country, 'name') })}
      </label>
      <div className="row">
        <button className="btn small primary" disabled={busy} onClick={save}>{busy ? t('Saving…') : t(saveText)}</button>
        {onSkip && <button className="btn small" disabled={busy} onClick={onSkip}>{t('Skip')}</button>}
        {onCancel && <button className="btn small ghost" disabled={busy} onClick={onCancel}>{t('Cancel')}</button>}
        {err && <span className="err">{err}</span>}
      </div>
    </div>)
}
