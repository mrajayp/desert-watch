import { useEffect, useState } from 'react'
import { api, qs } from '../api'
import { useApp } from '../App'
import { fmt } from '../charts/scales'
import ArticleRow from './ArticleRow'
import SourceFilter from './SourceFilter'
import { N_, t } from '../i18n'

const PAGE = 50
const LANGS = [['', N_('Any')], ['ar', N_('Arabic')], ['en', N_('English')]]
const SORTS = [['', N_('Newest')], ['pickup', N_('Most picked up')]]

// The articles behind one figure on a chart: `query` is passed to /api/items as-is
// (theme_id, region_id, start, end, lang …), so the count shown here matches the plotted value.
export default function ArticlesPanel({ title, subtitle, query, note }) {
  const { closePanel } = useApp()
  const [source, setSource] = useState('')
  const [lang, setLang] = useState(query.lang || '')
  // a chart that counts only some outlets (basis) opens on those, and the reader can widen it
  const [basis, setBasis] = useState(query.basis || '')
  const [sort, setSort] = useState('')
  const [data, setData] = useState(null)
  const params = (offset) => qs({ ...query, basis: basis || undefined, lang: lang || undefined, source: source || undefined, sort: sort || undefined, limit: PAGE, offset })
  const load = () => api('/api/items' + params(0)).then(setData)
  useEffect(() => { setData(null); load() }, [JSON.stringify(query), source, lang, basis, sort])
  const more = async () => {
    const r = await api('/api/items' + params(data.items.length))
    setData({ ...r, items: [...data.items, ...r.items] })
  }
  return (
    <aside className="drawer" aria-label={t('Articles')}>
      <div className="row" style={{ justifyContent: 'space-between', flexWrap: 'nowrap' }}>
        <div>
          <h2 style={{ margin: 0 }}>{title}</h2>
          {subtitle && <div className="small muted">{subtitle}</div>}
        </div>
        <button className="btn ghost" onClick={closePanel} aria-label={t('Close')}>✕</button>
      </div>
      {note && <p className="small muted">{note}</p>}
      <div className="row" style={{ margin: '8px 0', gap: 10 }}>
        <span className="stat"><span className="v num">{data ? fmt(data.total) : '…'}</span><span className="l">{t('articles', { n: data?.total })}</span></span>
        <span className="seg" role="group" aria-label={t('Language')}>
          {LANGS.map(([k, l]) =>
            <button key={k} aria-pressed={lang === k} onClick={() => setLang(k)}>{t(l)}</button>)}</span>
        {query.basis && (
          <span className="seg" role="group" aria-label={t('Outlets')}>
            <button aria-pressed={!!basis} onClick={() => setBasis(query.basis)} title={t('Only the outlets the chart counts')}>{t('Outlets followed all year')}</button>
            <button aria-pressed={!basis} onClick={() => setBasis('')}>{t('All sources')}</button></span>)}
        <span className="seg" role="group" aria-label={t('Order')}>
          {SORTS.map(([k, l]) =>
            <button key={k} aria-pressed={sort === k} onClick={() => setSort(k)}
              title={k ? t('Stories carried by the most outlets first') : undefined}>{t(l)}</button>)}</span>
      </div>
      <SourceFilter counts={data?.by_source} value={source} onChange={setSource} />
      {!data ? <div className="empty">{t('Loading…')}</div> : data.items.length === 0 ? <div className="empty">{t('No articles.')}</div> : (
        <>
          <ul className="list">{data.items.map((it) => <ArticleRow key={it.id} item={it} onChanged={load} context={{ from: 'chart' }} />)}</ul>
          {data.items.length < data.total && (
            <div className="row" style={{ justifyContent: 'center', marginTop: 10 }}>
              <button className="btn" onClick={more}>{t('Show {n} more', { n: Math.min(PAGE, data.total - data.items.length) })}</button>
            </div>)}
        </>)}
    </aside>
  )
}
