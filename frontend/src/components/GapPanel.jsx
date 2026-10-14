import { useEffect, useState } from 'react'
import { api, dwell, qs } from '../api'
import { useApp } from '../App'
import { MixBar } from '../charts/Balance'
import { INFO_FLAGS, DIMENSIONS, LENS_TEXT, flagText, fmt, gapLabel } from '../charts/scales'
import Comments from './Comments'
import ArticleRow from './ArticleRow'
import BlindSpots from './BlindSpots'

const VOTES = [
  ['real', 'Real gap', 'This is under-reported and worth covering'],
  ['covered', 'Already covered', 'Paste the link — it will count as coverage'],
  ['not_newsworthy', 'Not newsworthy', 'The signal is real but not a story'],
]

export default function GapPanel({ themeId, regionId }) {
  const { meta, filters, lang, closePanel, refresh, openAdd } = useApp()
  const [d, setD] = useState(null)
  const [voteNote, setVoteNote] = useState('')
  const [coveredUrl, setCoveredUrl] = useState('')
  const [pending, setPending] = useState(null)
  const [err, setErr] = useState(null)
  const [claimUrl, setClaimUrl] = useState('')
  const load = () => api('/api/gap' + qs({ theme_id: themeId, region_id: regionId, lens: filters.lens, week: filters.week })).then(setD)
  useEffect(() => { load() }, [themeId, regionId, filters.lens, filters.week])
  useEffect(() => dwell('gap', `${themeId}:${regionId}`, { lens: filters.lens }), [themeId, regionId, filters.lens])

  if (!d) return <aside className="drawer" aria-label="Gap detail"><div className="empty">Loading…</div></aside>
  const c = d.cell
  const lensInfo = LENS_TEXT[filters.lens]
  const myVote = d.votes.find((v) => v.mine && v.week === d.week)
  const myClaim = d.claims.find((x) => x.mine)
  const vote = async (v) => {
    if (v === 'covered' && !coveredUrl) { setPending('covered'); return }
    try {
      await api('/api/gap/vote', { method: 'POST', body: { theme_id: themeId, region_id: regionId, week: d.week, lens: filters.lens, vote: v, note: voteNote || null, covered_url: v === 'covered' ? coveredUrl : null } })
      setPending(null); setCoveredUrl(''); setErr(null); load(); refresh()
    } catch (e) { setErr(e.message) }
  }
  const claim = async (status) => {
    try {
      await api('/api/gap/claim', { method: 'POST', body: { theme_id: themeId, region_id: regionId, status, published_url: status === 'published' ? claimUrl : null } })
      setErr(null); load(); refresh()
    } catch (e) { setErr(e.message) }
  }
  const nm = (o) => (lang === 'ar' ? o.name_ar : o.name_en)
  const b = c?.breakdown || {}
  return (
    <aside className="drawer" aria-label="Gap detail">
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <div>
          <div className="small muted">{lensInfo.label} lens · window {d.window[0]} → {d.window[1]}</div>
          <h2 style={{ margin: '2px 0' }}>{nm(d.theme)} · {nm(d.region)}</h2>
          <div className="small ar" dir="rtl">{d.theme.name_ar} · {d.region.name_ar}</div>
        </div>
        <button className="btn ghost" onClick={closePanel} aria-label="Close">✕</button>
      </div>

      <div className="row" style={{ gap: 24, margin: '14px 0' }}>
        <div className="stat"><span className="v num">{fmt(c?.coverage ?? d.articles.total)}</span><span className="l">monitored articles</span></div>
        <div className="stat"><span className="v num">{fmt(c?.need ?? 0)}</span><span className="l">{lensInfo.unit}</span></div>
        <div className="stat"><span className="v" style={{ fontSize: 16, maxWidth: 200 }}>{c ? gapLabel(c.insufficient ? null : c.gap) : 'not scored'}</span>
          <span className="l">{b.reference === 'own_history' ? 'vs this theme’s previous 12 weeks' : 'vs comparable cells'}</span></div>
      </div>
      {c?.flags?.length > 0 && <div className="row">{c.flags.map((f) => <span key={f} className={INFO_FLAGS.has(f) ? "pill" : "pill flag"}>{flagText(f)}</span>)}</div>}
      {c && (
        <>
          <h3>Who is covering it</h3>
          <MixBar parts={b.scope || {}} labels={DIMENSIONS.scope.values}
            colors={{ libyan: 'var(--scope-libyan)', international: 'var(--scope-international)', diaspora: 'var(--scope-diaspora)' }} />
          <div style={{ height: 8 }} />
          <MixBar parts={b.lang || {}} labels={{ ar: 'Arabic', en: 'English', und: 'Unknown' }}
            colors={{ ar: 'var(--scope-libyan)', en: 'var(--scope-international)' }} />
          <BlindSpots compact />
          <p className="small muted">Previous 4 weeks: {fmt(b.prev_coverage)} articles vs {fmt(b.prev_need)} {lensInfo.unit}. Monitored sources only.</p>
        </>)}

      <h3>Is this a real gap?</h3>
      <div className="row">
        {VOTES.map(([k, label, hint]) => (
          <button key={k} className="btn" aria-pressed={myVote?.vote === k} title={hint} onClick={() => vote(k)}>{label}</button>))}
      </div>
      {pending === 'covered' && (
        <div className="row" style={{ marginTop: 8 }}>
          <input type="url" placeholder="https://… link to the coverage" value={coveredUrl} onChange={(e) => setCoveredUrl(e.target.value)} style={{ flex: 1 }} aria-label="Coverage link" />
          <button className="btn primary" disabled={!coveredUrl} onClick={() => vote('covered')}>Save</button>
        </div>)}
      <textarea style={{ marginTop: 8 }} dir="auto" placeholder="Optional: why? (stored with your vote)" value={voteNote} onChange={(e) => setVoteNote(e.target.value)} aria-label="Vote note" />
      {d.votes.length > 0 && <ul className="list small">{d.votes.slice(0, 8).map((v, i) =>
        <li key={i}><b>{v.user}</b> · {v.vote.replace('_', ' ')} <span className="muted">({v.week})</span>{v.note && <div dir="auto">{v.note}</div>}</li>)}</ul>}

      <h3>Working on it</h3>
      <div className="row">
        <button className="btn" aria-pressed={myClaim?.status === 'working'} onClick={() => claim('working')}>I’m working on this</button>
        <input type="url" placeholder="Published link" value={claimUrl} onChange={(e) => setClaimUrl(e.target.value)} aria-label="Published link" />
        <button className="btn" disabled={!claimUrl} onClick={() => claim('published')}>Mark published</button>
        {myClaim && <button className="btn ghost small" onClick={() => claim('dropped')}>Drop</button>}
      </div>
      {d.claims.filter((x) => x.status !== 'dropped').map((x, i) => <div key={i} className="small muted">{x.user}: {x.status}{x.published_url && <> · <a href={x.published_url} target="_blank" rel="noreferrer noopener">link</a></>}</div>)}
      <p className="small muted">Visible to your team only.</p>
      {err && <p className="err">{err}</p>}

      <h3>Discussion</h3>
      <Comments objectType="gap" objectKey={d.object_key} />

      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h3>Articles in window ({fmt(d.articles.total)})</h3>
        <button className="btn small" onClick={() => openAdd({ theme_ids: [themeId], region_ids: d.region.level === 'national' ? [] : [regionId] })}>+ Add missing article</button>
      </div>
      <ul className="list">{d.articles.items.map((it) => <ArticleRow key={it.id} item={it} onChanged={load} context={{ themeId, regionId }} />)}</ul>
      {d.statements?.total > 0 && (
        <>
          <h3>Official statements ({fmt(d.statements.total)})</h3>
          <p className="small muted">UN, embassy and government statements on this theme in the window. Not counted as coverage.</p>
          <ul className="list small">{d.statements.items.slice(0, 15).map((it) => (
            <li key={it.id}>{it.published_at.slice(0, 10)} · <a href={it.url} target="_blank" rel="noreferrer noopener" dir="auto">{it.title}</a> <span className="muted">· {it.outlet?.name}</span></li>))}</ul>
        </>)}
      {d.need_items.total > 0 && (
        <>
          <h3>Need signals ({fmt(d.need_items.total)})</h3>
          <ul className="list small">{d.need_items.items.slice(0, 20).map((it) => <li key={it.id}>{it.published_at.slice(0, 10)} · {it.title} <span className="muted num">{fmt(it.value)}</span></li>)}</ul>
        </>)}
      <p className="small muted" style={{ marginTop: 16 }}>Gap = how much less coverage there is than expected given the need signal. Small cells are pulled towards the reference, and cells below the minimum need are not scored.</p>
    </aside>
  )
}
