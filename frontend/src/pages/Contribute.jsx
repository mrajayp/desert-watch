import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { useApp } from '../App'
import { LENS_TEXT, RED_FROM, fmt, langName } from '../charts/scales'
import { lensNeed, verdictSentence, weekRange } from '../charts/trendText'
import AiPanelTask from '../components/AiPanelTask'
import ArticleRow, { replaceItem } from '../components/ArticleRow'
import { ErrorBox, Loading } from '../components/Notices'
import { LabelForm, NotCounted, ThemePills } from '../components/ThemeLabels'
import { useApi } from '../hooks/useApi'
import { useMutation } from '../hooks/useMutation'
import { usePageTitle } from '../hooks/usePageTitle'
import { fmtDate, isAr, pick, t, tn } from '../i18n'

const N_ = (s) => s // marks English for the catalogue; translated with t() when read

// codes the API sends, shown in the interface language
const MISSING = { scope: N_('scope'), alignment: N_('alignment') }
const SUGGESTION_STATUS = { pending: N_('pending'), accepted: N_('accepted'), rejected: N_('rejected') }
const code = (table, k) => (table[k] ? t(table[k]) : k)

// One place that tells a journalist where their input is needed right now, and why it matters.
export default function Contribute() {
  const { meta, me, openGap, openOutlet, openAdd, version, can } = useApp()
  usePageTitle(t('Contribute'))
  const q = useApi('/api/contribute', { deps: [version] })
  const d = q.data
  const nm = (o) => (o ? pick(o, 'name') : '—')
  const themes = new Map(meta.themes.map((th) => [th.id, th]))
  const regions = new Map(meta.regions.map((r) => [r.id, r]))
  if (!d) return <main className="page">{q.error ? <ErrorBox error={q.error} onRetry={q.retry} /> : <Loading />}</main>
  const ro = !can
  const red = meta.red_from ?? RED_FROM // one red threshold on every page: the API's
  // the lens's words for a gap's verdict sentence (pooled lenses compare with other topics)
  const needOf = (lens) => lensNeed(lens, meta.lenses.find((l) => l.key === lens)?.reference)
  // "Judge" opens the gap at its own lens and week; the page's saved lens is left alone
  const showGap = (g) => openGap(g.theme_id, g.region_id, { from: 'contribute', lens: g.lens, week: g.week })
  // a corrected row is replaced by the row the server sent back, so the queue stays and a second topic can follow
  const patchList = (key) => (r) => q.setData((x) => ({ ...x, [key]: Array.isArray(x[key]) ? replaceItem(x[key], r) : { ...x[key], items: replaceItem(x[key].items, r) } }))

  return (
    <main className="page">
      {q.error && <ErrorBox error={q.error} onRetry={q.retry} compact />}
      <section className="card">
        <div className="card-head">
          <div>
            <h2>{t('Contribute')}</h2>
            <p className="sub">{t('Desert Watch learns from what you tell it. Every vote, correction and rating below is saved as a training label, so the rankings and topic matching get better the more the team uses them. Pick anything; each task takes under a minute.')}</p>
          </div>
        </div>
        <Tally mine={d.mine} team={d.team} />
      </section>

      <div className="grid halves" style={{ marginTop: 16 }}>
        <Task n="1" title={t('Is this really a gap?')} why={t('The biggest gaps of the last 4 weeks that nobody has judged yet. Votes are shown on the gap and saved for the team. They will start to train the ranking once there are about 150 of them.')}
          empty={t('No unjudged gaps in the last 4 weeks.')}>
          {d.gaps.length > 0 && <ul className="list">{d.gaps.map((g) => {
            // articles = the count the score used; articles_all = every source (coverage until the API sends them)
            const n = g.articles ?? g.coverage
            const all = g.articles_all ?? g.coverage
            return (
            <li key={`${g.theme_id}:${g.region_id}`} className="row" style={{ justifyContent: 'space-between', flexWrap: 'nowrap' }}>
              <div>
                <b>{nm(themes.get(g.theme_id))}</b> · {nm(regions.get(g.region_id))}
                <div className="small muted">{verdictSentence(g, needOf(g.lens), red)} · {t('{articles} articles vs {need} {unit} ({lens} lens, week of {week})', {
                  articles: fmt(n), need: fmt(g.need), unit: LENS_TEXT[g.lens]?.unit ?? '', lens: LENS_TEXT[g.lens]?.label ?? '', week: weekRange(g.week),
                })}{all != null && all !== n && <span> · {t('{n} from all sources', { n: fmt(all) })}</span>}</div>
              </div>
              <button className="btn small primary" onClick={() => showGap(g)}>{t('Judge')}</button>
            </li>) })}</ul>}
        </Task>

        <Task n="2" title={t('Know something we missed?')} why={t('Most coverage on Facebook, and anything on Telegram or in print, does not reach us. Adding a link counts it as coverage, so the gap shrinks where it should.')}>
          {can && (
            <div className="row" style={{ gap: 8 }}>
              <button className="btn primary" onClick={() => openAdd()}>{t('+ Add an article')}</button>
            </div>)}
          <p className="small muted">{t('Tip: from any gap, “Already covered” takes a link too.')}</p>
        </Task>

        <Task n="3" title={t('What is this article about?')} why={t('The rules could not give these a topic ({n} in the last 2 weeks). Use Correct to pick topics, or mark junk.', { n: fmt(d.untagged.total) })}
          empty={t('Every recent article has a topic.')}>
          {d.untagged.items.length > 0 && <ul className="list">{d.untagged.items.map((it) => <ArticleRow key={it.id} item={it} onChanged={patchList('untagged')} context={{ from: 'contribute' }} />)}</ul>}
        </Task>

        <Task n="4" title={t('Where did it happen?')} why={t('These have a topic but no place ({n} in the last 2 weeks). Adding a district puts them on the map, and teaches the place matcher new spellings.', { n: fmt(d.unplaced.total) })}
          empty={t('Every recent filed article has a place.')}>
          {d.unplaced.items.length > 0 && <ul className="list">{d.unplaced.items.map((it) => <ArticleRow key={it.id} item={it} onChanged={patchList('unplaced')} context={{ from: 'contribute' }} />)}</ul>}
        </Task>

        <Task n="5" title={t('How good is this reporting?')} why={t('Rate accuracy, depth and local sourcing (1–3). Ratings build each outlet’s quality score; one article per busy outlet here.')}
          empty={t('Nothing waiting to be rated.')}>
          {d.to_assess.length > 0 && <ul className="list">{d.to_assess.map((it) => <ArticleRow key={it.id} item={it} onChanged={patchList('to_assess')} context={{ from: 'contribute' }} />)}</ul>}
        </Task>

        <Task n="6" title={t('Who is this outlet?')} why={t('{n} active outlets have no scope or political alignment on record. Categories need an evidence link; admins review proposals.', { n: fmt(d.outlets.total) })}
          empty={t('Every active outlet is categorised.')}>
          {d.outlets.items.length > 0 && <ul className="list">{d.outlets.items.map((o) => (
            <li key={o.id} className="row" style={{ justifyContent: 'space-between', flexWrap: 'nowrap' }}>
              <div><b dir="auto">{o.name}</b> <span className="small muted">{o.domain} · {tn(o.articles, '{count} article (12 wk)', '{count} articles (12 wk)', { count: fmt(o.articles) })} · {t('missing {what}', { what: o.missing.map((m) => code(MISSING, m)).join(t(' and ')) })}</span></div>
              <button className="btn small" onClick={() => openOutlet(o.id)}>{t('Categorise')}</button>
            </li>))}</ul>}
        </Task>
      </div>

      {can && <LearnQueue />}

      <section className="card" style={{ marginTop: 16 }}>
        <div className="card-head"><div><h2>{t('8. Suggest')}</h2>
          <p className="sub">{t('Sources to monitor, search words, place spellings or a gap you know about. An admin reviews each one; you will see its status here.')}</p></div></div>
        {can && <Suggest meta={meta} nm={nm} onSent={q.retry} />}
        {d.my_suggestions.length > 0 && (
          <>
            <h3>{t('Your suggestions')}</h3>
            <ul className="list small">{d.my_suggestions.map((x) => (
              <li key={x.id}>{fmtDate(x.at)} · <b>{SUGGEST_KINDS[x.kind] ? t(SUGGEST_KINDS[x.kind].label) : x.kind}</b>:<span dir="auto">{summary(x, themes, regions, nm)}</span> <span className="pill">{code(SUGGESTION_STATUS, x.status)}</span></li>))}</ul>
          </>)}
      </section>
      {me.role === 'admin' && <p className="small muted" style={{ marginTop: 8 }}>{t('Admins: suggestions arrive in Admin → Suggestions.')}</p>}

      <AiPanelTask n="9" ro={ro} />
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
  const items = [['votes', t('gap votes')], ['corrections', t('corrections')], ['assessments', t('ratings')], ['added', t('articles added')],
    ['comments', t('comments')], ['suggestions', t('suggestions')]]
  return (
    <div className="row" style={{ gap: 24, flexWrap: 'wrap', marginTop: 8 }}>
      <div className="small muted" style={{ alignSelf: 'center' }}>{t('You so far:')}</div>
      {items.map(([k, l]) => <div key={k} className="stat"><span className="v num">{fmt(mine[k] || 0)}</span><span className="l">{l}</span></div>)}
      <div className="small muted" style={{ alignSelf: 'center' }}>
        {t('Team, last 30 days: {people} people · {votes} votes · {corrections} corrections · {ratings} ratings · {added} added', {
          people: fmt(team.contributors), votes: fmt(team.votes), corrections: fmt(team.corrections), ratings: fmt(team.assessments), added: fmt(team.added),
        })}
      </div>
    </div>
  )
}

// The review queue: one article at a time, labelled with the full set of themes.
const QUEUE_REASON = {
  uncertain: (it, name) => (it.closest ? t('The classifier cannot tell if this is about {theme}.', { theme: name(it.closest) }) : t('The classifier is unsure about this one.')),
  gender_candidate: () => t('It mentions women but has no gender topic.'),
  generic_term: (it) => (it.generic_term ? t('Its topic rests on one common word (“{term}”).', { term: it.generic_term }) : t('Its topic rests on one common word.')),
}
const COUNT_KEY = 'dw_labels_given'

function LearnQueue() {
  const { meta } = useApp()
  const themeName = (slug) => pick(meta.themes.find((th) => th.slug === slug), 'name') || slug.replace(/_/g, ' ')
  const [i, setI] = useState(0)
  const [given, setGiven] = useState(() => { try { return +sessionStorage.getItem(COUNT_KEY) || 0 } catch { return 0 } })
  const skipped = useRef(new Set())
  const queue = useApi('/api/review-queue?n=20')
  useEffect(() => { setI(0) }, [queue.data])
  const items = (queue.data?.items || []).filter((x) => !skipped.current.has(x.id))
  const q = queue.data
  const it = items[i]
  const next = () => (i + 1 < items.length ? setI(i + 1) : queue.retry())
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
        <div><h2><span className="muted">7.</span> {t('Help the classifier learn')}</h2>
          <p className="sub">{t('Each label you give trains the classifier that sorts articles into themes. The queue shows articles the classifier or the word lists may have got wrong.')}</p></div>
        <div className="row" style={{ gap: 24 }}>
          <span className="stat"><span className="v num">{fmt(given)}</span><span className="l">{t('labels this session')}</span></span>
          {q && <span className="stat"><span className="v num">{fmt(q.labelled)}</span><span className="l">{t('articles labelled in all')}</span></span>}
        </div>
      </div>
      {!q && queue.error ? <ErrorBox error={queue.error} onRetry={queue.retry} />
        : !q || queue.refreshing ? <Loading />
          : !it ? (
            <div className="row"><span className="small muted">{t('Nothing left to label right now.')}</span>
              <button className="btn small" onClick={() => { skipped.current.clear(); queue.retry() }}>{t('Look again')}</button></div>)
            : (
                <div>
                  <div className="small muted">{t('Article {i} of {total}', { i: i + 1, total: q.items.length })} · {QUEUE_REASON[it.reason]?.(it, themeName) || it.reason}</div>
                  <h3 style={{ margin: '6px 0 2px', fontSize: 15, color: 'var(--ink)' }}>
                    <a href={it.url} target="_blank" rel="noreferrer noopener" dir="auto">{it.title}</a></h3>
                  <div className="small muted">{it.outlet?.name || '—'} · {fmtDate(it.published_at)} · {langName(it.lang)}</div>
                  {it.snippet && <p dir="auto" style={{ margin: '8px 0', maxWidth: 820 }}>{it.snippet.length > 400 ? `${it.snippet.slice(0, 400)}…` : it.snippet}</p>}
                  <div className="row small" style={{ margin: '6px 0' }}>
                    <span className="muted">{t('Counted now:')}</span>
                    {it.theme_ids.length ? <ThemePills item={it} /> : <span className="muted">{t('no topic')}</span>}
                  </div>
                  <NotCounted item={it} />
                  <div style={{ marginTop: 12 }}>
                    <LabelForm key={it.id} item={it} saveText={t('Save and next')} onSaved={saved} onSkip={skip} />
                  </div>
                </div>)}
    </section>
  )
}

const SUGGEST_KINDS = {
  source: { label: N_('Source to monitor'), hint: N_('A website, Facebook page or Telegram channel we should follow') },
  keyword: { label: N_('Search word'), hint: N_('A word or phrase that should count towards a topic') },
  alias: { label: N_('Place spelling'), hint: N_('Another way a district or town is written') },
  gap: { label: N_('Gap I know about'), hint: N_('A topic and place that is under-reported (feeds the Journalists lens)') },
}

function summary(x, themes, regions, nm) {
  const p = x.payload || {}
  const arrow = isAr() ? '←' : '→'
  if (x.kind === 'source') return p.url
  if (x.kind === 'keyword') return `“${p.term}” ${arrow} ${nm(themes.get(+p.theme_id))}`
  if (x.kind === 'alias') return `“${p.alias}” = ${nm(regions.get(+p.region_id))}`
  if (x.kind === 'gap') return `${nm(themes.get(+p.theme_id))} · ${nm(regions.get(+p.region_id))}`
  return ''
}

function Suggest({ meta, nm, onSent }) {
  const [kind, setKind] = useState('source')
  const [p, setP] = useState({})
  const [msg, setMsg] = useState(null)
  const set = (patch) => setP({ ...p, ...patch })
  const places = meta.regions.filter((r) => r.level !== 'macro')
  const ok = { source: p.url, keyword: p.term && p.theme_id, alias: p.alias && p.region_id, gap: p.theme_id && p.region_id }[kind]
  const send = useMutation((e) => { e.preventDefault(); return api('/api/suggestions', { method: 'POST', body: { kind, payload: p } }) },
    { onSuccess: () => { setMsg(t('Thanks, sent for review.')); setP({}); onSent() } })
  return (
    <form className="form" onSubmit={(e) => send.run(e)}>
      <div className="seg" role="group" aria-label={t('Suggestion type')}>
        {Object.entries(SUGGEST_KINDS).map(([k, v]) => <button type="button" key={k} aria-pressed={kind === k} onClick={() => { setKind(k); setP({}); setMsg(null) }}>{t(v.label)}</button>)}
      </div>
      <p className="small muted">{t(SUGGEST_KINDS[kind].hint)}</p>
      {kind === 'source' && <input type="url" required placeholder={t('https://… (site, Facebook page or t.me channel)')} value={p.url || ''} onChange={(e) => set({ url: e.target.value })} aria-label={t('Source link')} />}
      {(kind === 'keyword' || kind === 'gap') && (
        <select required value={p.theme_id || ''} onChange={(e) => set({ theme_id: e.target.value })} aria-label={t('Topic')}>
          <option value="">{t('Topic…')}</option>{meta.themes.map((th) => <option key={th.id} value={th.id}>{nm(th)}</option>)}</select>)}
      {kind === 'keyword' && <input required dir="auto" placeholder={t('Word or phrase (Arabic or English)')} value={p.term || ''} onChange={(e) => set({ term: e.target.value })} aria-label={t('Search word')} />}
      {(kind === 'alias' || kind === 'gap') && (
        <select required value={p.region_id || ''} onChange={(e) => set({ region_id: e.target.value })} aria-label={t('Place')}>
          <option value="">{t('Place…')}</option>{places.map((r) => <option key={r.id} value={r.id}>{nm(r)}</option>)}</select>)}
      {kind === 'alias' && <input required dir="auto" placeholder={t('Spelling as it appears in articles')} value={p.alias || ''} onChange={(e) => set({ alias: e.target.value })} aria-label={t('Place spelling')} />}
      <textarea dir="auto" placeholder={t('Why? (optional)')} value={p.note || ''} onChange={(e) => set({ note: e.target.value })} aria-label={t('Note')} />
      <div className="row"><button className="btn primary" disabled={!ok || send.busy}>{t('Send suggestion')}</button>{msg && <span className="small">{msg}</span>}</div>
      {send.error && <ErrorBox error={send.error} compact />}
    </form>
  )
}
