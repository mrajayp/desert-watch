import { useEffect, useState } from 'react'
import { api, qs } from '../api'
import { useApp } from '../App'
import { DIMENSIONS } from '../charts/scales'
import { fmtDate, fmtNum, isAr, t, tn } from '../i18n'

const N_ = (s) => s // marks English for the catalogue; translated with t() when shown
import Comments from './Comments'
import ArticleRow from './ArticleRow'
import OutletReach from './OutletReach'
import { countryName } from '../charts/RegionalNetwork'

// Codes from the API (config/outlet_taxonomy.yaml). English shows them as they are; Arabic translates them.
const DIM_NAME = {
  type: N_('Ownership type'), scope: N_('Scope'), alignment: N_('Political alignment'), medium: N_('Medium'),
  reach: N_('Reach tier'), scrape_source_type: N_('Social-media scrape: source type (2023-24)'),
  scrape_affiliation: N_('Social-media scrape: affiliation (2023-24)'),
}
// values DIMENSIONS has no label for. The scrape's own labels stay exactly as published.
const RAW_VALUE = {
  medium: {
    website: N_('website'), tv: N_('tv'), radio: N_('radio'), facebook: N_('facebook'), instagram: N_('instagram'),
    telegram: N_('telegram'), x: N_('x'), tiktok: N_('tiktok'), youtube: N_('youtube'), print: N_('print'),
  },
  reach: { national: N_('national'), regional: N_('regional'), local: N_('local'), niche: N_('niche'), unknown: N_('unknown') },
}
const CONFIDENCE = { reported: N_('reported'), likely: N_('likely'), disputed: N_('disputed'), unverified: N_('unverified') }
const STATUS = { proposed: N_('proposed'), active: N_('active'), rejected: N_('rejected') }
// keys of the 2023-24 scrape figures, shown as "fb posts 1,234"
const SCRAPE_KEY = {
  articles: N_('articles {value}'), fb_posts: N_('fb posts {value}'), fb_engagement: N_('fb engagement {value}'), tweets: N_('tweets {value}'),
  posts: N_('posts {value}'), interactions: N_('interactions {value}'), comments: N_('comments {value}'), shares: N_('shares {value}'),
}
const code = (table, k) => (table[k] ? t(table[k]) : k)
const dimName = (d) => (isAr() ? d.name_ar || (DIM_NAME[d.key] ? t(DIM_NAME[d.key]) : d.name) : d.name)
// ISO dates stay as they are in English; Arabic gets Libyan month names
const day = (s) => (isAr() && s ? fmtDate(s) : s)
// a decimal as the API sends it (4.2), with the interface language's decimal mark
const num = (v) => fmtNum(v, { useGrouping: false })

export default function OutletPanel({ id }) {
  const { me, meta, closePanel, refresh } = useApp()
  const [o, setO] = useState(null)
  const [hist, setHist] = useState([])
  const [tax, setTax] = useState(null)
  const [items, setItems] = useState(null)
  const [form, setForm] = useState({ dimension: 'alignment', value: '', confidence: 'reported', evidence_url: '', note: '' })
  const [base, setBase] = useState('')
  const [msg, setMsg] = useState(null)
  const [aiCited, setAiCited] = useState(null) // AI answers audit: null when the user may not see it
  const load = async () => {
    const all = await api('/api/outlets' + qs({ days: 365 }))
    setO(all.find((x) => x.id === id))
    api(`/api/outlets/${id}`).then((r) => setAiCited(typeof r?.ai_cited_4w === 'number' ? r.ai_cited_4w : null)).catch(() => setAiCited(null))
    setHist(await api(`/api/outlets/${id}/history`))
    setItems(await api('/api/items' + qs({ outlet_id: id, days: 84, limit: 20 })))
  }
  useEffect(() => { load(); api('/api/outlets/taxonomy').then(setTax) }, [id])
  if (!o || !tax) return <aside className="drawer"><div className="empty">{t('Loading…')}</div></aside>
  const dim = tax.dimensions.find((d) => d.key === form.dimension)
  const submit = async (e) => {
    e.preventDefault()
    try {
      const r = await api(`/api/outlets/${id}/categories`, { method: 'POST', body: { ...form, note: form.note || null } })
      setMsg(r.status === 'active' ? t('Applied.') : t('Proposed — an admin will review it.'))
      setForm({ ...form, value: '', evidence_url: '', note: '' }); load(); refresh()
    } catch (ex) { setMsg(ex.message) }
  }
  const review = async (cid, approve) => { await api(`/api/outlets/categories/${cid}/review`, { method: 'POST', body: { approve } }); load(); refresh() }
  const setLocation = async () => {
    const isCity = base in (meta.country.cities || {})
    await api(`/api/outlets/${id}`, { method: 'PATCH', body: isCity ? { base_city: base } : { base_country: base } })
    setBase(''); load(); refresh()
  }
  // DIMENSIONS labels are already in the interface language (charts/scales.js)
  const label = (d, v) => DIMENSIONS[d]?.values?.[v] || code(RAW_VALUE[d] || {}, v)
  const histDim = (key) => {
    const d = tax.dimensions.find((x) => x.key === key)
    return d ? dimName(d) : undefined
  }
  return (
    <aside className="drawer" aria-label={t('Outlet')}>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <div><h2 style={{ margin: 0 }}><span dir="auto">{o.name}</span></h2><div className="small muted">{o.domain} · {o.created_via === 'auto' ? t('found automatically') : t('seeded')} · {t('{n} articles (12 months)', { n: o.articles })}</div></div>
        <button className="btn ghost" onClick={closePanel} aria-label={t('Close')}>✕</button>
      </div>
      <h3>{t('Current profile')}</h3>
      <table className="data"><tbody>
        <tr><th>{t('Base')}</th><td>{o.base_city || countryName(o.base_country) || <span className="muted">{t('not set')}</span>}</td></tr>
        {tax.dimensions.map((d) => {
          const c = o.categories[d.key]
          return <tr key={d.key}><th>{dimName(d)}{d.contested && <span className="muted small"> ({t('contested')})</span>}</th>
            <td>{c ? <>{d.third_party && <span className="muted small">{t('as published:')} </span>}{label(d.key, c.value)} <span className="pill">{code(CONFIDENCE, c.confidence)}</span>{' '}
              {c.evidence_url?.startsWith('http') ? <a className="small" href={c.evidence_url} target="_blank" rel="noreferrer noopener">{t('evidence')} ↗</a>
                : <span className="small muted">{t('source: Social Media scraped data (2023–24)')}</span>}</> : <span className="muted">{t('unclassified')}</span>}</td></tr>
        })}
        {o.monitored === false && <tr><th>{t('Collection')}</th><td><span className="pill">{t('partly seen')}</span> <span className="small muted">{t('Facebook page: we only see the posts Google News indexes')}</span></td></tr>}
        {o.external?.social_media_scrape && <tr><th>{t('Social-media scrape')}</th><td className="small">
          {Object.entries(o.external.social_media_scrape).filter(([k]) => !['source', 'period', 'link', 'kind'].includes(k)).map(([k, v]) => (SCRAPE_KEY[k] ? t(SCRAPE_KEY[k], { value: fmtNum(Number(v)) }) : `${k.replace('_', ' ')} ${fmtNum(Number(v))}`)).join(' · ')}
          <div className="muted">{t('Social Media scraped data, {from} to {to}', { from: o.external.social_media_scrape.period?.from ?? '', to: o.external.social_media_scrape.period?.to ?? '' })}</div></td></tr>}
        {o.quality && <tr><th>{t('Quality (team)')}</th><td>{t('accuracy {accuracy} · depth {depth} · local voices {local}', { accuracy: num(o.quality.accuracy), depth: num(o.quality.depth), local: num(o.quality.local_sourcing) })} <span className="muted">(n={o.quality.n})</span></td></tr>}
      </tbody></table>
      {typeof aiCited === 'number' && <p className="small" style={{ margin: '8px 0 0' }}>{tn(aiCited, 'Cited by AI assistants: {n} time in 4 weeks', 'Cited by AI assistants: {n} times in 4 weeks')}</p>}
      <OutletReach id={id} />

      {me.role === 'admin' && (
        <div className="row" style={{ marginTop: 10 }}>
          <input list="cities" placeholder={t('Base city or country')} value={base} onChange={(e) => setBase(e.target.value)} />
          <datalist id="cities">{Object.keys(meta.country.cities || {}).map((c) => <option key={c} value={c} />)}</datalist>
          <button className="btn small" disabled={!base} onClick={setLocation}>{t('Set base')}</button>
        </div>)}

      <h3>{me.role === 'admin' ? t('Set a category') : t('Suggest a category')}</h3>
      <form className="form" onSubmit={submit}>
        <div className="row">
          <select value={form.dimension} onChange={(e) => setForm({ ...form, dimension: e.target.value, value: '' })} aria-label={t('Dimension')}>
            {tax.dimensions.map((d) => <option key={d.key} value={d.key}>{dimName(d)}</option>)}</select>
          <select value={form.value} onChange={(e) => setForm({ ...form, value: e.target.value })} aria-label={t('Value')} required>
            <option value="">{t('choose…')}</option>{dim.values.map((v) => <option key={v} value={v}>{label(dim.key, v)}</option>)}</select>
          <select value={form.confidence} onChange={(e) => setForm({ ...form, confidence: e.target.value })} aria-label={t('Confidence')}>
            {tax.confidence_levels.map((c) => <option key={c} value={c}>{code(CONFIDENCE, c)}</option>)}</select>
        </div>
        <input type="url" required placeholder={t('Evidence link (study, ownership record, outlet’s own page…)')} value={form.evidence_url} onChange={(e) => setForm({ ...form, evidence_url: e.target.value })} />
        <textarea dir="auto" placeholder={t('Note (optional)')} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
        {dim.contested && <p className="small muted">{t('Contested label: quote the source’s own wording in the note. Shown as “classified as … per [source]”, team-only.')}</p>}
        <div className="row"><button className="btn primary" disabled={!form.value || !form.evidence_url}>{me.role === 'admin' ? t('Apply') : t('Propose')}</button>{msg && <span className="small">{msg}</span>}</div>
      </form>

      <h3>{t('History')}</h3>
      {hist.length === 0 ? <p className="muted small">{t('No category records.')}</p> : (
        <ul className="list small">{hist.map((h) => (
          <li key={h.id}><b>{histDim(h.dimension)}</b>: {label(h.dimension, h.value)} · {code(CONFIDENCE, h.confidence)} · {code(STATUS, h.status)}
            · {h.valid_to ? t('{from} → {to}', { from: day(h.valid_from), to: day(h.valid_to) }) : t('{from} → now', { from: day(h.valid_from) })} {h.set_by && <>· {t('by {name}', { name: h.set_by })}</>} · <a href={h.evidence_url} target="_blank" rel="noreferrer noopener">{t('evidence')}</a>
            {h.note && <div className="muted" dir="auto">{h.note}</div>}
            {h.status === 'proposed' && me.role === 'admin' && <div className="row"><button className="btn small" onClick={() => review(h.id, true)}>{t('Approve')}</button><button className="btn small ghost" onClick={() => review(h.id, false)}>{t('Reject')}</button></div>}
          </li>))}</ul>)}
      <h3>{t('Recent articles')}</h3>
      <ul className="list">{items?.items.map((it) => <ArticleRow key={it.id} item={it} onChanged={load} />)}</ul>
      <h3>{t('Discussion')}</h3>
      <Comments objectType="outlet" objectKey={String(id)} />
    </aside>
  )
}
