import { useState } from 'react'
import { api, qs } from '../api'
import { useApp } from '../App'
import { dimLabel, dimValue } from '../charts/scales'
import { useApi } from '../hooks/useApi'
import { useMutation } from '../hooks/useMutation'
import { usePageTitle } from '../hooks/usePageTitle'
import { fmtDate, fmtMonth, fmtNum, isAr, t, tn } from '../i18n'
import { outletPath } from '../routes'

const N_ = (s) => s // marks English for the catalogue; translated with t() when shown
import Comments from './Comments'
import ArticleRow, { replaceItem } from './ArticleRow'
import CopyLink from './CopyLink'
import Dialog from './Dialog'
import { ErrorBox, Loading } from './Notices'
import OutletReach from './OutletReach'
import { countryName } from '../charts/countries'

// Codes from the API (config/outlet_taxonomy.yaml) get their words from charts/scales.js (dimLabel,
// dimValue), the same words the map tooltip uses. The scrape's own labels stay exactly as published.
const CONFIDENCE = { reported: N_('reported'), likely: N_('likely'), disputed: N_('disputed'), unverified: N_('unverified') }
const STATUS = { proposed: N_('proposed'), active: N_('active'), rejected: N_('rejected') }
// keys of the 2023-24 scrape figures, shown as "fb posts 1,234"
const SCRAPE_KEY = {
  articles: N_('articles {value}'), fb_posts: N_('fb posts {value}'), fb_engagement: N_('fb engagement {value}'), tweets: N_('tweets {value}'),
  posts: N_('posts {value}'), interactions: N_('interactions {value}'), comments: N_('comments {value}'), shares: N_('shares {value}'),
}
const code = (table, k) => (table[k] ? t(table[k]) : k)
// the taxonomy's own name for a dimension (name / name_ar), else the shared words
const dimName = (d) => (isAr() ? d.name_ar || dimLabel(d.key) : d.name || dimLabel(d.key))
// a decimal as the API sends it (4.2), with the interface language's decimal mark
const num = (v) => fmtNum(v, { useGrouping: false })

// One outlet: /outlets/:id. Its profile, reach, categories (with evidence), recent articles, discussion.
// GET /api/outlets/{id} is the one outlet's full row (the same shape as a row of GET /api/outlets, plus
// ai_cited_4w and closed_on); the history, the articles and the taxonomy load alongside it, not after it.
export default function OutletPanel({ id }) {
  const { me, meta, closePanel, refresh, can } = useApp()
  const detail = useApi(`/api/outlets/${id}`)
  const hist = useApi(`/api/outlets/${id}/history`)
  const items = useApi('/api/items' + qs({ outlet_id: id, days: 84, limit: 20 }))
  const tax = useApi('/api/outlets/taxonomy')
  const [form, setForm] = useState({ dimension: 'alignment', value: '', confidence: 'reported', evidence_url: '', note: '' })
  const [base, setBase] = useState('')
  const [closedOn, setClosedOn] = useState('')
  const [msg, setMsg] = useState(null)
  const o = detail.data
  usePageTitle(o?.name || t('Outlet'))
  // AI answers audit: only when the user may see it
  const aiCited = typeof o?.ai_cited_4w === 'number' ? o.ai_cited_4w : null
  const reloadAll = () => { detail.retry(); hist.retry(); refresh() }
  const submit = useMutation((e) => { e.preventDefault(); return api(`/api/outlets/${id}/categories`, { method: 'POST', body: { ...form, note: form.note || null } }) },
    { onSuccess: (r) => { setMsg(r.status === 'active' ? t('Applied.') : t('Proposed — an admin will review it.')); setForm({ ...form, value: '', evidence_url: '', note: '' }); reloadAll() } })
  const review = useMutation((cid, approve) => api(`/api/outlets/categories/${cid}/review`, { method: 'POST', body: { approve } }), { onSuccess: reloadAll })
  const setLocation = useMutation(() => {
    const isCity = base in (meta.country.cities || {})
    return api(`/api/outlets/${id}`, { method: 'PATCH', body: isCity ? { base_city: base } : { base_country: base } })
  }, { onSuccess: () => { setBase(''); reloadAll() } })
  // an outlet that closed or became unreachable keeps counting in the comparisons up to that day, so its
  // silence shows as a real drop (null reopens it)
  const setClosed = useMutation((value) => api(`/api/outlets/${id}`, { method: 'PATCH', body: { closed_on: value } }),
    { onSuccess: () => { setClosedOn(''); reloadAll() } })

  const ready = o && tax.data
  const loadError = detail.error || tax.error
  const retry = () => { detail.retry(); tax.retry() }
  const dim = tax.data?.dimensions.find((d) => d.key === form.dimension)
  const label = dimValue
  const histDim = (key) => {
    const d = tax.data.dimensions.find((x) => x.key === key)
    return d ? dimName(d) : undefined
  }
  // the row's article count covers the list's default 12 weeks unless the API says it counted a year (articles_days)
  const articleCount = o?.articles == null ? null
    : (o.articles_days ?? 84) >= 365 ? t('{n} articles (12 months)', { n: o.articles }) : t('{n} articles (12 weeks)', { n: o.articles })
  const subtitle = o && <>{o.domain}{o.created_via ? <> · {o.created_via === 'auto' ? t('found automatically') : t('seeded')}</> : null}{articleCount ? <> · {articleCount}</> : null}</>
  return (
    <Dialog title={<span dir="auto">{o?.name || t('Outlet')}</span>} subtitle={subtitle} onClose={closePanel} actions={<CopyLink path={outletPath(id)} objectType="outlet" objectKey={id} />}>
      {!ready && loadError && <ErrorBox error={loadError} onRetry={retry} />}
      {!ready && !loadError && <Loading />}
      {ready && (
        <>
          {loadError && <ErrorBox error={loadError} onRetry={retry} compact />}
          <h3>{t('Current profile')}</h3>
          <table className="data"><tbody>
            <tr><th>{t('Base')}</th><td>{o.base_city || countryName(o.base_country) || <span className="muted">{t('not set')}</span>}</td></tr>
            {tax.data.dimensions.map((d) => {
              const c = (o.categories || {})[d.key]
              return <tr key={d.key}><th>{dimName(d)}{d.contested && <span className="muted small"> ({t('contested')})</span>}</th>
                <td>{c ? <>{d.third_party && <span className="muted small">{t('as published:')} </span>}{label(d.key, c.value)} <span className="pill">{code(CONFIDENCE, c.confidence)}</span>{' '}
                  {c.evidence_url?.startsWith('http') ? <a className="small" href={c.evidence_url} target="_blank" rel="noreferrer noopener">{t('evidence')} ↗</a>
                    : <span className="small muted">{t('source: Social Media scraped data (2023–24)')}</span>}</> : <span className="muted">{t('unclassified')}</span>}</td></tr>
            })}
            {o.monitored === false && <tr><th>{t('Collection')}</th><td><span className="pill">{t('partly seen')}</span> <span className="small muted">{t('Facebook page: we only see the posts Google News indexes')}</span></td></tr>}
            {o.closed_on && <tr><th>{t('Closed')}</th><td><span className="pill">{t('closed on {date}', { date: fmtDate(o.closed_on) })}</span> <span className="small muted">{t('Its earlier articles still count, so its silence shows as a real drop.')}</span></td></tr>}
            {o.external?.social_media_scrape && <tr><th>{t('Social-media scrape')}</th><td className="small">
              {Object.entries(o.external.social_media_scrape).filter(([k]) => !['source', 'period', 'link', 'kind'].includes(k)).map(([k, v]) => (SCRAPE_KEY[k] ? t(SCRAPE_KEY[k], { value: fmtNum(Number(v)) }) : `${k.replace('_', ' ')} ${fmtNum(Number(v))}`)).join(' · ')}
              <div className="muted">{t('Social Media scraped data, {from} to {to}', { from: fmtMonth(o.external.social_media_scrape.period?.from ?? ''), to: fmtMonth(o.external.social_media_scrape.period?.to ?? '') })}</div></td></tr>}
            {o.quality && <tr><th>{t('Quality (team)')}</th><td>{t('accuracy {accuracy} · depth {depth} · local voices {local}', { accuracy: num(o.quality.accuracy), depth: num(o.quality.depth), local: num(o.quality.local_sourcing) })} <span className="muted">(n={o.quality.n})</span></td></tr>}
          </tbody></table>
          {typeof aiCited === 'number' && <p className="small" style={{ margin: '8px 0 0' }}>{tn(aiCited, 'Cited by AI assistants: {n} time in 4 weeks', 'Cited by AI assistants: {n} times in 4 weeks')}</p>}
          <OutletReach id={id} />

          {me.role === 'admin' && (
            <div className="row" style={{ marginTop: 10 }}>
              <input list="cities" placeholder={t('Base city or country')} value={base} onChange={(e) => setBase(e.target.value)} />
              <datalist id="cities">{Object.keys(meta.country.cities || {}).map((c) => <option key={c} value={c} />)}</datalist>
              <button className="btn small" disabled={!base || setLocation.busy} onClick={() => setLocation.run()}>{t('Set base')}</button>
              {setLocation.error && <ErrorBox error={setLocation.error} compact />}
            </div>)}
          {me.role === 'admin' && (
            <div className="row" style={{ marginTop: 6 }}>
              <label className="small">{t('Closed on')} <input type="date" value={closedOn} onChange={(e) => setClosedOn(e.target.value)} aria-label={t('Closing date')} /></label>
              <button className="btn small" disabled={!closedOn || setClosed.busy} onClick={() => setClosed.run(closedOn)}>{t('Mark closed')}</button>
              {o.closed_on && <button className="btn small ghost" disabled={setClosed.busy} onClick={() => setClosed.run(null)}>{t('Reopen')}</button>}
              {setClosed.error && <ErrorBox error={setClosed.error} compact />}
            </div>)}

          {can && (
            <>
              <h3>{me.role === 'admin' ? t('Set a category') : t('Suggest a category')}</h3>
              <form className="form" onSubmit={(e) => submit.run(e)}>
                <div className="row">
                  <select value={form.dimension} onChange={(e) => setForm({ ...form, dimension: e.target.value, value: '' })} aria-label={t('Dimension')}>
                    {tax.data.dimensions.map((d) => <option key={d.key} value={d.key}>{dimName(d)}</option>)}</select>
                  <select value={form.value} onChange={(e) => setForm({ ...form, value: e.target.value })} aria-label={t('Value')} required>
                    <option value="">{t('choose…')}</option>{dim.values.map((v) => <option key={v} value={v}>{label(dim.key, v)}</option>)}</select>
                  <select value={form.confidence} onChange={(e) => setForm({ ...form, confidence: e.target.value })} aria-label={t('Confidence')}>
                    {tax.data.confidence_levels.map((c) => <option key={c} value={c}>{code(CONFIDENCE, c)}</option>)}</select>
                </div>
                <input type="url" required placeholder={t('Evidence link (study, ownership record, outlet’s own page…)')} value={form.evidence_url} onChange={(e) => setForm({ ...form, evidence_url: e.target.value })} />
                <textarea dir="auto" placeholder={t('Note (optional)')} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
                {dim.contested && <p className="small muted">{t('Contested label: quote the source’s own wording in the note. Shown as “classified as … per [source]”, team-only.')}</p>}
                <div className="row"><button className="btn primary" disabled={!form.value || !form.evidence_url || submit.busy}>{me.role === 'admin' ? t('Apply') : t('Propose')}</button>{msg && <span className="small">{msg}</span>}</div>
                {submit.error && <ErrorBox error={submit.error} compact />}
              </form>
            </>)}

          <h3>{t('History')}</h3>
          {hist.error && !hist.data && <ErrorBox error={hist.error} onRetry={hist.retry} compact />}
          {hist.data && hist.data.length === 0 ? <p className="muted small">{t('No category records.')}</p> : hist.data && (
            <ul className="list small">{hist.data.map((h) => (
              <li key={h.id}><b>{histDim(h.dimension)}</b>: {label(h.dimension, h.value)} · {code(CONFIDENCE, h.confidence)} · {code(STATUS, h.status)}
                · {h.valid_to ? t('{from} → {to}', { from: fmtDate(h.valid_from), to: fmtDate(h.valid_to) }) : t('{from} → now', { from: fmtDate(h.valid_from) })} {h.set_by &&<>· {t('by {name}', { name: h.set_by })}</>} · <a href={h.evidence_url} target="_blank" rel="noreferrer noopener">{t('evidence')}</a>
                {h.note && <div className="muted" dir="auto">{h.note}</div>}
                {h.status === 'proposed' && me.role === 'admin' && <div className="row"><button className="btn small" disabled={review.busy} onClick={() => review.run(h.id, true)}>{t('Approve')}</button><button className="btn small ghost" disabled={review.busy} onClick={() => review.run(h.id, false)}>{t('Reject')}</button></div>}
              </li>))}</ul>)}
          {review.error && <ErrorBox error={review.error} compact />}
          <h3>{t('Recent articles')}</h3>
          {items.error && !items.data && <ErrorBox error={items.error} onRetry={items.retry} compact />}
          <ul className="list">{items.data?.items.map((it) => <ArticleRow key={it.id} item={it} onChanged={(r) => items.setData((d) => ({ ...d, items: replaceItem(d.items, r) }))} context={{ from: 'outlet' }} />)}</ul>
          <h3>{t('Discussion')}</h3>
          <Comments objectType="outlet" objectKey={String(id)} />
        </>)}
    </Dialog>
  )
}
