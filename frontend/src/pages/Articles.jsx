import { useEffect, useMemo, useState } from 'react'
import { useLocation, useSearchParams } from 'react-router-dom'
import { api, qs } from '../api'
import { useApp } from '../App'
import { fmt } from '../charts/scales'
import ArticleRow, { replaceItem } from '../components/ArticleRow'
import { ErrorBox, Loading } from '../components/Notices'
import SourceFilter from '../components/SourceFilter'
import { useApi } from '../hooks/useApi'
import { useMutation } from '../hooks/useMutation'
import { usePageTitle } from '../hooks/usePageTitle'
import { N_, fmtDate, isAr, pick, t } from '../i18n'
import { articlesQuery } from '../routes'

const PAGE = 50
const PERIODS = [[1, N_('Last 24 hours')], [7, N_('Last 7 days')], [28, N_('Last 4 weeks')], [90, N_('Last 3 months')]]
const LANGS = [['', N_('Any')], ['ar', N_('Arabic')], ['en', N_('English')]]
// a day (YYYY-MM-DD): as is in English, with Libyan month names in Arabic
const day = (d) => (isAr() ? fmtDate(d) : d)

// Every monitored article, newest first. The filters are the URL:
// /articles?theme=&region=&days=&start=&end=&lang=&source=&q=&basis= (chart click-throughs link here,
// with their title and note in history state so the list says what it is a list of).
export default function Articles() {
  const { meta } = useApp()
  usePageTitle(t('Articles'))
  const [sp, setSp] = useSearchParams()
  const loc = useLocation()
  const f = useMemo(() => articlesQuery(sp), [sp])
  const [q, setQ] = useState(f.q)
  // a chart that counts only some outlets (basis) opens on those; the toggle stays while on this page
  const [hadBasis] = useState(!!f.basis)
  const nm = (o) => pick(o, 'name')
  // URL words: theme, region, days, start, end, lang, source, q, basis ('' removes the parameter)
  const set = (patch) => setSp((prev) => {
    const n = new URLSearchParams(prev)
    for (const [k, v] of Object.entries(patch)) { if (v == null || v === '') n.delete(k); else n.set(k, String(v)) }
    return n
  }, { replace: true })
  const params = (offset) => qs({ ...f, limit: PAGE, offset })
  const list = useApi('/api/items' + params(0))
  const data = list.data
  const more = useMutation(async () => {
    const r = await api('/api/items' + params(data.items.length))
    list.setData((d) => ({ ...r, items: [...d.items, ...r.items] }))
  })
  useEffect(() => { const h = setTimeout(() => { if ((f.q || '') !== q) set({ q }) }, 350); return () => clearTimeout(h) }, [q]) // eslint-disable-line react-hooks/exhaustive-deps
  const custom = !!(f.start || f.end)
  const ctx = loc.state || {}

  return (
    <main className="page">
      <section className="card">
        <div className="card-head">
          <div><h2>{ctx.title ? <span dir="auto">{ctx.title}</span> : t('Articles')} {data && `(${fmt(data.total)})`}</h2>
            <p className="sub">{ctx.subtitle || t('Everything Desert Watch has collected that passed the {country} relevance check, newest first. Use Fix on a row to correct its topic or place.', { country: pick(meta.country, 'name') })}</p>
            {ctx.note && <p className="small muted">{ctx.note}</p>}</div>
        </div>
        <div className="row" style={{ gap: 10, flexWrap: 'wrap' }}>
          <select value={custom ? 'custom' : f.days} onChange={(e) => e.target.value !== 'custom' && set({ days: +e.target.value, start: '', end: '' })} aria-label={t('Period')}>
            {custom && <option value="custom">{t('{from} → {to}', { from: day(f.start) || '…', to: day(f.end) || '…' })}</option>}
            {PERIODS.map(([d, l]) => <option key={d} value={d}>{t(l)}</option>)}</select>
          <select value={f.theme_id} onChange={(e) => set({ theme: e.target.value })} aria-label={t('Theme')}>
            <option value="">{t('All themes')}</option>
            {meta.themes.map((th) => <option key={th.id} value={th.id}>{nm(th)}</option>)}</select>
          <select value={f.region_id} onChange={(e) => set({ region: e.target.value })} aria-label={t('Place')}>
            <option value="">{t('All places')}</option>
            {meta.regions.filter((r) => r.level !== 'national').map((r) => <option key={r.id} value={r.id}>{r.level === 'macro' ? '▸ ' : ''}{nm(r)}</option>)}</select>
          <span className="seg" role="group" aria-label={t('Language')}>
            {LANGS.map(([k, l]) =>
              <button key={k} aria-pressed={f.lang === k} onClick={() => set({ lang: k })}>{t(l)}</button>)}</span>
          {(hadBasis || f.basis) && (
            <span className="seg" role="group" aria-label={t('Outlets')}>
              <button aria-pressed={!!f.basis} onClick={() => set({ basis: 'trend' })} title={t('Only the outlets the chart counts')}>{t('Outlets followed all year')}</button>
              <button aria-pressed={!f.basis} onClick={() => set({ basis: '' })}>{t('All sources')}</button></span>)}
          <input type="search" dir="auto" placeholder={t('Words in the headline')} value={q} onChange={(e) => setQ(e.target.value)} aria-label={t('Search headlines')} />
        </div>
        <SourceFilter counts={data?.by_source} value={f.source} onChange={(source) => set({ source })} />
        {!data && list.error && <ErrorBox error={list.error} onRetry={list.retry} />}
        {!data && !list.error && <Loading />}
        {data && list.error && <ErrorBox error={list.error} onRetry={list.retry} compact />}
        {data && (data.items.length === 0 ? <div className="empty">{t('No articles match.')}</div> : (
          <>
            <ul className="list" style={list.refreshing ? { opacity: 0.6 } : undefined}>{data.items.map((it) => <ArticleRow key={it.id} item={it} onChanged={(r) => list.setData((d) => ({ ...d, items: replaceItem(d.items, r) }))} context={{ from: ctx.from || 'articles' }} />)}</ul>
            {more.error && <ErrorBox error={more.error} compact />}
            {data.items.length < data.total && (
              <div className="row" style={{ justifyContent: 'center', marginTop: 10 }}>
                <button className="btn" disabled={more.busy} onClick={() => more.run()}>{t('Show {n} more', { n: Math.min(PAGE, data.total - data.items.length) })}</button>
              </div>)}
          </>))}
      </section>
    </main>
  )
}
