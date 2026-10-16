import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { useApp } from '../App'
import { LENS_TEXT, fmt, gapLabel } from '../charts/scales'
import ArticleRow from '../components/ArticleRow'
import { LabelForm, NotCounted, ThemePills } from '../components/ThemeLabels'

// One place that tells a journalist where their input is needed right now, and why it matters.
export default function Contribute() {
  const { meta, lang, me, openGap, openOutlet, openAdd, setFilters, version } = useApp()
  const [d, setD] = useState(null)
  const load = () => api('/api/contribute').then(setD)
  useEffect(() => { load() }, [version])
  const nm = (o) => (o ? (lang === 'ar' ? o.name_ar : o.name_en) : '—')
  const themes = new Map(meta.themes.map((t) => [t.id, t]))
  const regions = new Map(meta.regions.map((r) => [r.id, r]))
  if (!d) return <main className="page"><div className="empty">Loading…</div></main>
  const ro = !d.can_contribute
  const showGap = (g) => { setFilters({ lens: g.lens, week: g.week }); openGap(g.theme_id, g.region_id, { from: 'contribute' }) }

  return (
    <main className="page">
      <section className="card">
        <div className="card-head">
          <div>
            <h2>Contribute</h2>
            <p className="sub">Desert Watch learns from what you tell it. Every vote, correction and rating below is saved as a training
              label, so the rankings and topic matching get better the more the team uses them. Pick anything; each task takes under a minute.</p>
          </div>
        </div>
        {ro && <p className="pill flag" style={{ display: 'inline-block' }}>Your account is read-only. Ask an admin for journalist access to vote, correct, rate and suggest.</p>}
        <Tally mine={d.mine} team={d.team} />
      </section>

      <div className="grid halves" style={{ marginTop: 16 }}>
        <Task n="1" title="Is this really a gap?" why="The biggest gaps of the last 4 weeks that nobody has judged yet. Your vote decides whether they stay at the top."
          empty="No unjudged gaps in the last 4 weeks.">
          {d.gaps.length > 0 && <ul className="list">{d.gaps.map((g) => (
            <li key={`${g.theme_id}:${g.region_id}`} className="row" style={{ justifyContent: 'space-between', flexWrap: 'nowrap' }}>
              <div>
                <b>{nm(themes.get(g.theme_id))}</b> · {nm(regions.get(g.region_id))}
                <div className="small muted">{gapLabel(g.gap)} · {fmt(g.coverage)} articles vs {fmt(g.need)} {LENS_TEXT[g.lens]?.unit} ({LENS_TEXT[g.lens]?.label} lens, week of {g.week})</div>
              </div>
              <button className="btn small primary" onClick={() => showGap(g)}>Judge</button>
            </li>))}</ul>}
        </Task>

        <Task n="2" title="Know something we missed?" why="Most coverage on Facebook, and anything on Telegram or in print, does not reach us. Adding a link counts it as coverage, so the gap shrinks where it should.">
          <div className="row" style={{ gap: 8 }}>
            <button className="btn primary" disabled={ro} onClick={() => openAdd()}>+ Add an article</button>
          </div>
          <p className="small muted">Tip: from any gap, “Already covered” takes a link too.</p>
        </Task>

        <Task n="3" title="What is this article about?" why={`The rules could not give these a topic (${fmt(d.untagged.total)} in the last 2 weeks). Use Fix to pick topics, or mark junk.`}
          empty="Every recent article has a topic.">
          {d.untagged.items.length > 0 && <ul className="list">{d.untagged.items.map((it) => <ArticleRow key={it.id} item={it} onChanged={load} context={{ from: 'contribute' }} />)}</ul>}
        </Task>

        <Task n="4" title="Where did it happen?" why={`These have a topic but no place (${fmt(d.unplaced.total)} in the last 2 weeks). Adding a district puts them on the map, and teaches the place matcher new spellings.`}
          empty="Every recent filed article has a place.">
          {d.unplaced.items.length > 0 && <ul className="list">{d.unplaced.items.map((it) => <ArticleRow key={it.id} item={it} onChanged={load} context={{ from: 'contribute' }} />)}</ul>}
        </Task>

        <Task n="5" title="How good is this reporting?" why="Rate accuracy, depth and local sourcing (1–3). Ratings build each outlet’s quality score; one article per busy outlet here."
          empty="Nothing waiting to be rated.">
          {d.to_assess.length > 0 && <ul className="list">{d.to_assess.map((it) => <ArticleRow key={it.id} item={it} onChanged={load} context={{ from: 'contribute' }} />)}</ul>}
        </Task>

        <Task n="6" title="Who is this outlet?" why={`${fmt(d.outlets.total)} active outlets have no scope or political alignment on record. Categories need an evidence link; admins review proposals.`}
          empty="Every active outlet is categorised.">
          {d.outlets.items.length > 0 && <ul className="list">{d.outlets.items.map((o) => (
            <li key={o.id} className="row" style={{ justifyContent: 'space-between', flexWrap: 'nowrap' }}>
              <div><b>{o.name}</b> <span className="small muted">{o.domain} · {fmt(o.articles)} articles (12 wk) · missing {o.missing.join(' and ')}</span></div>
              <button className="btn small" onClick={() => openOutlet(o.id)}>Categorise</button>
            </li>))}</ul>}
        </Task>
      </div>

      <LearnQueue ro={ro} />

      <section className="card" style={{ marginTop: 16 }}>
        <div className="card-head"><div><h2>8. Suggest</h2>
          <p className="sub">Sources to monitor, search words, place spellings or a gap you know about. An admin reviews each one; you will see its status here.</p></div></div>
        <Suggest meta={meta} nm={nm} onSent={load} ro={ro} />
        {d.my_suggestions.length > 0 && (
          <>
            <h3>Your suggestions</h3>
            <ul className="list small">{d.my_suggestions.map((x) => (
              <li key={x.id}>{x.at.slice(0, 10)} · <b>{SUGGEST_KINDS[x.kind]?.label || x.kind}</b>: {summary(x, themes, regions, nm)} <span className="pill">{x.status}</span></li>))}</ul>
          </>)}
      </section>
      {me.role === 'admin' && <p className="small muted" style={{ marginTop: 8 }}>Admins: suggestions arrive in Admin → Suggestions.</p>}
    </main>
  )
}

function Task({ n, title, why, empty, children }) {
  const hasContent = Array.isArray(children) ? children.some(Boolean) : Boolean(children)
  return (
    <section className="card">
      <h2 style={{ marginTop: 0 }}><span className="muted">{n}.</span> {title}</h2>
      <p className="sub">{why}</p>
      {hasContent ? children : <p className="small muted">{empty}</p>}
    </section>
  )
}

function Tally({ mine, team }) {
  const items = [['votes', 'gap votes'], ['corrections', 'corrections'], ['assessments', 'ratings'], ['added', 'articles added'],
    ['comments', 'comments'], ['suggestions', 'suggestions']]
  return (
    <div className="row" style={{ gap: 24, flexWrap: 'wrap', marginTop: 8 }}>
      <div className="small muted" style={{ alignSelf: 'center' }}>You so far:</div>
      {items.map(([k, l]) => <div key={k} className="stat"><span className="v num">{fmt(mine[k] || 0)}</span><span className="l">{l}</span></div>)}
      <div className="small muted" style={{ alignSelf: 'center' }}>
        Team, last 30 days: {fmt(team.contributors)} people · {fmt(team.votes)} votes · {fmt(team.corrections)} corrections · {fmt(team.assessments)} ratings · {fmt(team.added)} added
      </div>
    </div>
  )
}

// The review queue: one article at a time, labelled with the full set of themes.
const QUEUE_REASON = {
  uncertain: (it, name) => (it.closest ? `The classifier cannot tell if this is about ${name(it.closest)}.` : 'The classifier is unsure about this one.'),
  gender_candidate: () => 'It mentions women but has no gender topic.',
  generic_term: (it) => `Its topic rests on one common word${it.generic_term ? ` (“${it.generic_term}”)` : ''}.`,
}
const COUNT_KEY = 'dw_labels_given'

function LearnQueue({ ro }) {
  const { meta } = useApp()
  const themeName = (slug) => meta.themes.find((t) => t.slug === slug)?.name_en || slug.replace(/_/g, ' ')
  const [q, setQ] = useState(null)
  const [i, setI] = useState(0)
  const [err, setErr] = useState(null)
  const [given, setGiven] = useState(() => { try { return +sessionStorage.getItem(COUNT_KEY) || 0 } catch { return 0 } })
  const skipped = useRef(new Set())
  const load = () => {
    setQ(null); setErr(null)
    api('/api/review-queue?n=20').then((r) => { setQ({ ...r, items: r.items.filter((x) => !skipped.current.has(x.id)) }); setI(0) })
      .catch((e) => setErr(e.message))
  }
  useEffect(() => { if (!ro) load() }, [ro])
  const it = q?.items[i]
  const next = () => (i + 1 < q.items.length ? setI(i + 1) : load())
  const saved = () => {
    const n = given + 1
    setGiven(n)
    try { sessionStorage.setItem(COUNT_KEY, String(n)) } catch { /* no storage */ }
    next()
  }
  const skip = () => { skipped.current.add(it.id); next() }
  return (
    <section className="card" style={{ marginTop: 16 }}>
      <div className="card-head">
        <div><h2><span className="muted">7.</span> Help the classifier learn</h2>
          <p className="sub">Each label you give trains the classifier that sorts articles into themes, and the queue shows the articles it is least sure about.</p></div>
        <div className="row" style={{ gap: 24 }}>
          <span className="stat"><span className="v num">{fmt(given)}</span><span className="l">labels this session</span></span>
          {q && <span className="stat"><span className="v num">{fmt(q.labelled)}</span><span className="l">articles labelled in all</span></span>}
        </div>
      </div>
      {ro ? <p className="small muted">Your account is read-only, so you cannot label articles yet.</p>
        : err ? <p className="err">{err}</p>
          : !q ? <div className="empty">Loading…</div>
            : !it ? (
              <div className="row"><span className="small muted">Nothing left to label right now.</span>
                <button className="btn small" onClick={() => { skipped.current.clear(); load() }}>Look again</button></div>)
              : (
                <div>
                  <div className="small muted">Article {i + 1} of {q.items.length} · {QUEUE_REASON[it.reason]?.(it, themeName) || it.reason}</div>
                  <h3 style={{ margin: '6px 0 2px', fontSize: 15, color: 'var(--ink)' }}>
                    <a href={it.url} target="_blank" rel="noreferrer noopener" dir="auto">{it.title}</a></h3>
                  <div className="small muted">{it.outlet?.name || '—'} · {it.published_at.slice(0, 10)} · {it.lang?.toUpperCase()}</div>
                  {it.snippet && <p dir="auto" style={{ margin: '8px 0', maxWidth: 820 }}>{it.snippet.length > 400 ? `${it.snippet.slice(0, 400)}…` : it.snippet}</p>}
                  <div className="row small" style={{ margin: '6px 0' }}>
                    <span className="muted">Counted now:</span>
                    {it.theme_ids.length ? <ThemePills item={it} /> : <span className="muted">no topic</span>}
                  </div>
                  <NotCounted item={it} />
                  <div style={{ marginTop: 12 }}>
                    <LabelForm key={it.id} item={it} saveText="Save and next" onSaved={saved} onSkip={skip} />
                  </div>
                </div>)}
    </section>
  )
}

const SUGGEST_KINDS = {
  source: { label: 'Source to monitor', hint: 'A website, Facebook page or Telegram channel we should follow' },
  keyword: { label: 'Search word', hint: 'A word or phrase that should count towards a topic' },
  alias: { label: 'Place spelling', hint: 'Another way a district or town is written' },
  gap: { label: 'Gap I know about', hint: 'A topic and place that is under-reported (feeds the Journalists lens)' },
}

function summary(x, themes, regions, nm) {
  const p = x.payload || {}
  if (x.kind === 'source') return p.url
  if (x.kind === 'keyword') return `“${p.term}” → ${nm(themes.get(+p.theme_id))}`
  if (x.kind === 'alias') return `“${p.alias}” = ${nm(regions.get(+p.region_id))}`
  if (x.kind === 'gap') return `${nm(themes.get(+p.theme_id))} · ${nm(regions.get(+p.region_id))}`
  return ''
}

function Suggest({ meta, nm, onSent, ro }) {
  const [kind, setKind] = useState('source')
  const [p, setP] = useState({})
  const [msg, setMsg] = useState(null)
  const set = (patch) => setP({ ...p, ...patch })
  const places = meta.regions.filter((r) => r.level !== 'macro')
  const ok = { source: p.url, keyword: p.term && p.theme_id, alias: p.alias && p.region_id, gap: p.theme_id && p.region_id }[kind]
  const send = async (e) => {
    e.preventDefault()
    try {
      await api('/api/suggestions', { method: 'POST', body: { kind, payload: p } })
      setMsg('Thanks, sent for review.'); setP({}); onSent()
    } catch (ex) { setMsg(ex.message) }
  }
  return (
    <form className="form" onSubmit={send}>
      <div className="seg" role="group" aria-label="Suggestion type">
        {Object.entries(SUGGEST_KINDS).map(([k, v]) => <button type="button" key={k} aria-pressed={kind === k} onClick={() => { setKind(k); setP({}); setMsg(null) }}>{v.label}</button>)}
      </div>
      <p className="small muted">{SUGGEST_KINDS[kind].hint}</p>
      {kind === 'source' && <input type="url" required placeholder="https://… (site, Facebook page or t.me channel)" value={p.url || ''} onChange={(e) => set({ url: e.target.value })} aria-label="Source link" />}
      {(kind === 'keyword' || kind === 'gap') && (
        <select required value={p.theme_id || ''} onChange={(e) => set({ theme_id: e.target.value })} aria-label="Topic">
          <option value="">Topic…</option>{meta.themes.map((t) => <option key={t.id} value={t.id}>{nm(t)}</option>)}</select>)}
      {kind === 'keyword' && <input required dir="auto" placeholder="Word or phrase (Arabic or English)" value={p.term || ''} onChange={(e) => set({ term: e.target.value })} aria-label="Search word" />}
      {(kind === 'alias' || kind === 'gap') && (
        <select required value={p.region_id || ''} onChange={(e) => set({ region_id: e.target.value })} aria-label="Place">
          <option value="">Place…</option>{places.map((r) => <option key={r.id} value={r.id}>{nm(r)}</option>)}</select>)}
      {kind === 'alias' && <input required dir="auto" placeholder="Spelling as it appears in articles" value={p.alias || ''} onChange={(e) => set({ alias: e.target.value })} aria-label="Place spelling" />}
      <textarea dir="auto" placeholder="Why? (optional)" value={p.note || ''} onChange={(e) => set({ note: e.target.value })} aria-label="Note" />
      <div className="row"><button className="btn primary" disabled={!ok || ro}>Send suggestion</button>{msg && <span className="small">{msg}</span>}</div>
    </form>
  )
}
