import { useEffect, useState } from 'react'
import { api } from '../api'
import { useApp } from '../App'
import SourceHealth from '../components/SourceHealth'
import { fmtDate, fmtNum, isAr, pick, t, tn } from '../i18n'
import { Markdown } from './Digest'

const N_ = (s) => s // marks English for the catalogue; translated with t() when read

const split = (s) => s.split(/\n|,|،/).map((x) => x.trim()).filter(Boolean)

// codes the API sends (roles, statuses, kinds), shown in the interface language; unknown codes as they are
const CODE = {
  admin: N_('admin'), journalist: N_('journalist'), viewer: N_('viewer'),
  all: N_('all'), active: N_('active'), disabled: N_('disabled'), rejected: N_('rejected'), pending: N_('pending'), accepted: N_('accepted'),
  new: N_('new'), answered: N_('answered'), planned: N_('planned'), done: N_('done'), closed: N_('closed'),
  suggestion: N_('suggestion'), question: N_('question'), problem: N_('problem'),
  source: N_('source'), keyword: N_('keyword'), alias: N_('alias'), gap: N_('gap'), outlet_category: N_('outlet_category'),
  user: N_('user'), model: N_('model'),
}
const code = (k) => (CODE[k] ? t(CODE[k]) : k)
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1)
const THRESHOLD_NAMES = { theme_classifier_new_labels: N_('theme classifier new labels'), gap_ranker_votes: N_('gap ranker votes') }
// list separators in the interface language
const comma = () => (isAr() ? '، ' : ', ')
const semi = () => (isAr() ? '؛ ' : '; ')
// a day (YYYY-MM-DD): as is in English, with Libyan month names in Arabic
const day = (d) => (isAr() ? fmtDate(d) : d)

export default function Admin() {
  const { refresh } = useApp()
  const [themes, setThemes] = useState([])
  const [edit, setEdit] = useState(null)
  const [preview, setPreview] = useState(null)
  const [invite, setInvite] = useState({ email: '', role: 'journalist' })
  const [inviteLink, setInviteLink] = useState(null)
  const [sugs, setSugs] = useState([])
  const [learning, setLearning] = useState(null)
  const [msg, setMsg] = useState(null)
  const load = () => {
    api('/api/themes').then(setThemes)
    api('/api/admin/suggestions').then(setSugs)
    api('/api/admin/learning').then(setLearning)
  }
  useEffect(() => { load() }, [])
  const startEdit = (th) => { setPreview(null); setEdit(th ? { ...th, en: th.en_terms.join('\n'), ar: th.ar_terms.join('\n'), ex: th.exclude.join('\n') } : { id: null, name_en: '', name_ar: '', en: '', ar: '', ex: '', active: true }) }
  const body = () => ({ name_en: edit.name_en, name_ar: edit.name_ar, en_terms: split(edit.en), ar_terms: split(edit.ar), exclude: split(edit.ex), active: edit.active,
    acled_event_types: edit.acled_event_types || [], reliefweb_themes: edit.reliefweb_themes || [] })
  // tid: the preview uses the saved theme's word pairs and exceptions, which this form does not edit
  const runPreview = async () => setPreview(await api(`/api/themes/preview${edit.id ? `?tid=${edit.id}` : ''}`, { method: 'POST', body: body() }))
  const saveTheme = async () => {
    await api(edit.id ? `/api/themes/${edit.id}` : '/api/themes', { method: edit.id ? 'PUT' : 'POST', body: body() })
    setMsg(t('Saved. Articles are being re-tagged and scores recomputed in the background.')); setEdit(null); load(); setTimeout(refresh, 4000)
  }
  const sendInvite = async (e) => {
    e.preventDefault()
    const r = await api('/api/admin/invites', { method: 'POST', body: invite })
    setInviteLink(location.origin + r.invite_path); setInvite({ email: '', role: 'journalist' })
  }
  const review = async (id, accept) => { await api(`/api/admin/suggestions/${id}`, { method: 'POST', body: { accept } }); load() }
  const run = async (job) => { await api(`/api/admin/run/${job}`, { method: 'POST' }); setMsg(t('Queued {job}. Refresh in a minute.', { job })) }

  return (
    <main className="page">
      {msg && <div className="banner info">{msg}</div>}
      <div className="grid halves">
        <section className="card">
          <div className="card-head"><h2>{t('Themes')}</h2><button className="btn small" onClick={() => startEdit(null)}>{t('+ New theme')}</button></div>
          <p className="sub">{t('Editing a theme bumps its version and re-tags all articles. Arabic terms only apply to RSS and Google News (GDELT can’t search Arabic script).')}</p>
          <ul className="list">{themes.map((th) => (
            <li key={th.id} className="row" style={{ justifyContent: 'space-between' }}>
              <span><b>{th.name_en}</b> <span className="ar" dir="rtl">{th.name_ar}</span> <span className="muted small">{t('v{version} · {en} EN / {ar} AR terms', { version: th.version, en: th.en_terms.length, ar: th.ar_terms.length })}{!th.active && ` · ${t('inactive')}`}</span></span>
              <button className="btn small" onClick={() => startEdit(th)}>{t('Edit')}</button></li>))}</ul>
          {edit && (
            <div className="form" style={{ marginTop: 12 }}>
              <div className="row"><label style={{ flex: 1 }}>{t('Name (EN)')}<input type="text" value={edit.name_en} onChange={(e) => setEdit({ ...edit, name_en: e.target.value })} /></label>
                <label style={{ flex: 1 }}>{t('Name (AR)')}<input type="text" dir="rtl" value={edit.name_ar} onChange={(e) => setEdit({ ...edit, name_ar: e.target.value })} /></label></div>
              <div className="grid halves">
                <label>{t('English terms (one per line)')}<textarea rows={7} value={edit.en} onChange={(e) => setEdit({ ...edit, en: e.target.value })} /></label>
                <label>{t('Arabic terms')}<textarea rows={7} dir="rtl" value={edit.ar} onChange={(e) => setEdit({ ...edit, ar: e.target.value })} /></label>
              </div>
              <label>{t('Exclusions (veto a match)')}<textarea rows={2} value={edit.ex} onChange={(e) => setEdit({ ...edit, ex: e.target.value })} /></label>
              <label className="row"><input type="checkbox" checked={edit.active} onChange={(e) => setEdit({ ...edit, active: e.target.checked })} />{t('Active')}</label>
              <div className="row"><button className="btn" onClick={runPreview}>{t('Preview matches (30 days)')}</button><span className="spacer" />
                <button className="btn ghost" onClick={() => setEdit(null)}>{t('Cancel')}</button><button className="btn primary" disabled={!edit.name_en} onClick={saveTheme}>{t('Save')}</button></div>
              {preview && (
                <div>
                  <p className="small">{t('Matches {matched} of {scanned} recent articles. Top terms: {terms}', {
                    matched: preview.matched, scanned: preview.scanned, terms: preview.top_terms.slice(0, 8).map(([term, k]) => `${term} (${k})`).join(comma()),
                  })}</p>
                  <ul className="list small scroll" style={{ maxHeight: 260 }}>{preview.samples.map((s) => (
                    <li key={s.id}><span dir="auto">{s.title}</span> <span className="muted">[{s.hits.join(comma())}]</span>{!s.relevant && <span className="pill flag">{t('marked junk')}</span>}</li>))}</ul>
                  <p className="small muted">{t('Check precision before saving: if fewer than ~8 in 10 samples are on-topic, tighten terms or add exclusions.')}</p>
                </div>)}
            </div>)}
        </section>
        <section className="card">
          <h2>{t('Invite a journalist')}</h2>
          <form className="row" onSubmit={sendInvite}>
            <input type="email" required placeholder={t('email')} value={invite.email} onChange={(e) => setInvite({ ...invite, email: e.target.value })} />
            <select value={invite.role} onChange={(e) => setInvite({ ...invite, role: e.target.value })}><option value="journalist">{cap(code('journalist'))}</option><option value="admin">{cap(code('admin'))}</option></select>
            <button className="btn primary">{t('Create invite')}</button>
          </form>
          {inviteLink && <p className="small">{t('Send this link privately (valid 7 days):')} <code dir="ltr" style={{ wordBreak: 'break-all' }}>{inviteLink}</code></p>}

          <h2 style={{ marginTop: 20 }}>{t('Suggestions queue ({n})', { n: sugs.length })}</h2>
          {sugs.length === 0 ? <p className="muted small">{t('Nothing pending.')}</p> : (
            <ul className="list small">{sugs.map((g) => (
              <li key={g.id}><b>{code(g.kind)}</b> {t('by {who}', { who: g.user || code(g.origin) })} · <span className="mono" dir="ltr">{JSON.stringify(g.payload)}</span>
                <div className="row"><button className="btn small" onClick={() => review(g.id, true)}>{t('Accept')}</button><button className="btn small ghost" onClick={() => review(g.id, false)}>{t('Reject')}</button></div></li>))}</ul>)}

          <h2 style={{ marginTop: 20 }}>{t('Learning')}</h2>
          {learning && (
            <div className="small">
              <p>{t('Labels: {list} ({explicit} explicit, {implicit} implicit)', {
                list: Object.entries(learning.labels).map(([k, v]) => `${k} ${v}`).join(' · ') || t('none yet'),
                explicit: learning.by_origin.explicit || 0, implicit: learning.by_origin.implicit || 0,
              })}</p>
              <p>{t('Behaviour events: {list}', { list: Object.entries(learning.events).map(([k, v]) => `${k} ${v}`).join(' · ') || t('none yet') })}</p>
              <p>{t('Vote agreement: {unanimous} of {multiple} gaps with 2+ votes are unanimous.', { unanimous: learning.vote_agreement.unanimous, multiple: learning.vote_agreement.gaps_with_multiple_votes })}</p>
              {learning.rule_confirmation && Object.keys(learning.rule_confirmation).length > 0 && (
                <>
                  <p style={{ marginBottom: 4 }}><b>{t('Precision proxy')}</b> — {t('share of search results (last 28 days) whose theme the keyword rules confirm. Low = the search returns loosely related items, or the rules miss vocabulary:')}</p>
                  <table className="data"><thead><tr><th>{t('Theme / language')}</th><th className="num">{t('Items')}</th><th className="num">{t('Confirmed')}</th></tr></thead>
                    <tbody>{Object.entries(learning.rule_confirmation).map(([k, v]) => (
                      <tr key={k}><td>{k}</td><td className="num">{v.n}</td><td className="num">{Math.round(v.confirmed * 100)}%{v.confirmed < 0.5 && <span className="pill flag" style={{ marginInlineStart: 6 }}>{t('review terms')}</span>}</td></tr>))}</tbody></table>
                </>)}
              <p className="muted">{t('Models switch on at: {list}. Until then rankings are rule-based.', {
                list: Object.entries(learning.thresholds).map(([k, v]) => `${THRESHOLD_NAMES[k] ? t(THRESHOLD_NAMES[k]) : k.replace(/_/g, ' ')} ≥ ${v}`).join(semi()),
              })}</p>
            </div>)}
        </section>
      </div>
      <ModelsCard />
      <MethodsCard />
      <UsersCard />
      <FeedbackCard />
      <AlertsCard />
      <section className="card" style={{ marginTop: 16 }}>
        <div className="card-head"><h2>{t('Data sources')}</h2>
          <div className="row">{['rss', 'youtube', 'galerts', 'gnews', 'gnews_social', 'digest', 'gdelt', 'gdelt_timeline', 'wikipedia', 'recompute'].map((j) => <button key={j} className="btn small" onClick={() => run(j)}>{t('Run {job}', { job: j })}</button>)}</div></div>
        <SourceHealth />
      </section>
    </main>
  )
}

function AlertsCard() {
  const [data, setData] = useState(null)
  const [lines, setLines] = useState('')
  const [result, setResult] = useState(null)
  const [filter, setFilter] = useState('')
  const load = () => api('/api/admin/alerts').then(setData)
  useEffect(() => { load() }, [])
  if (!data) return null
  const attached = data.alerts.filter((a) => a.feed_url).length
  const shown = data.alerts.filter((a) => !filter || a.key.includes(filter) || a.label.toLowerCase().includes(filter.toLowerCase()))
  const save = async () => { setResult(await api('/api/admin/alerts', { method: 'POST', body: { lines } })); setLines(''); load() }
  const copy = (s) => navigator.clipboard?.writeText(s)
  return (
    <section className="card" style={{ marginTop: 16 }}>
      <div className="card-head">
        <div><h2>{t('Google Alerts ({attached} of {total} connected)', { attached, total: data.alerts.length })}</h2>
          <p className="sub">{t('Create each alert at google.com/alerts with: {settings}. Then paste its RSS feed URL below. Alerts collect from the day they are created.', {
            settings: Object.entries(data.settings).map(([k, v]) => `${k}: ${v}`).join(' · '),
          })}</p></div>
        <input type="text" placeholder={t('Filter (e.g. district, sabha, :ar)')} value={filter} onChange={(e) => setFilter(e.target.value)} aria-label={t('Filter alerts')} />
      </div>
      <div className="scroll" style={{ maxHeight: 360 }}>
        <table className="data">
          <thead><tr><th>{t('Key')}</th><th>{t('Label')}</th><th>{t('Query')}</th><th>{t('Feed')}</th></tr></thead>
          <tbody>{shown.map((a) => (
            <tr key={a.key}>
              <td className="mono">{a.key}</td><td dir="auto">{a.label}</td>
              <td><code dir="ltr" style={{ unicodeBidi: "isolate" }}>{a.query}</code> <button className="btn small ghost" onClick={() => copy(a.query)} title={t('Copy query')}>{t('Copy')}</button></td>
              <td className="small">{a.feed_url ? (a.last_error ? <span className="err">{t('error')}</span> : a.last_ok_at ? tn(a.last_items, 'ok · {n} item', 'ok · {n} items') : t('connected')) : <span className="muted">{t('not connected')}</span>}</td>
            </tr>))}</tbody>
        </table>
      </div>
      <h3>{t('Connect feeds')}</h3>
      <textarea rows={4} className="mono" dir="ltr" value={lines} onChange={(e) => setLines(e.target.value)}
        placeholder={'district:sabha:ar https://www.google.com/alerts/feeds/…/…\ntheme:health:en https://www.google.com/alerts/feeds/…/…'} // i18n-ok: a sample of alert keys and feed URLs, not English prose
      />
      <div className="row" style={{ marginTop: 6 }}>
        <button className="btn primary" disabled={!lines.trim()} onClick={save}>{t('Connect')}</button>
        {result && <span className="small">{t('{n} connected', { n: result.attached })}{result.problems.length ? ` · ${t('problems: {list}', { list: result.problems.join(semi()) })}` : ''}</span>}
      </div>
    </section>
  )
}

function UsersCard() {
  const { me, refresh } = useApp()
  const [users, setUsers] = useState([])
  const [err, setErr] = useState(null)
  const [show, setShow] = useState('all')
  const load = () => api('/api/admin/users').then(setUsers)
  useEffect(() => { load() }, [])
  const patch = async (u, body) => {
    setErr(null)
    try { await api(`/api/admin/users/${u.id}`, { method: 'PATCH', body }); load(); refresh() } catch (e) { setErr(e.message) }
  }
  const pending = users.filter((u) => u.status === 'pending')
  const rest = users.filter((u) => u.status !== 'pending' && (show === 'all' || u.status === show))
  const ROLE_HELP = { admin: t('everything, incl. users & themes'), journalist: t('vote, comment, add & correct'), viewer: t('read-only') }
  return (
    <section className="card" style={{ marginTop: 16 }}>
      <h2>{t('Users and access')}</h2>
      <p className="sub">{t('People can request access from the sign-in page. Approve them with a role, or reject. Roles: {roles}.', {
        roles: Object.entries(ROLE_HELP).map(([r, h]) => `${code(r)} (${h})`).join(' · '),
      })}</p>
      {err && <p className="err">{err}</p>}
      <h3>{t('Access requests ({n})', { n: pending.length })}</h3>
      {pending.length === 0 ? <p className="small muted">{t('No pending requests.')}</p> : (
        <ul className="list">{pending.map((u) => <PendingRow key={u.id} u={u} onDecide={patch} />)}</ul>)}
      <div className="row" style={{ justifyContent: 'space-between', marginTop: 12 }}>
        <h3 style={{ margin: 0 }}>{t('All users ({n})', { n: users.length - pending.length })}</h3>
        <span className="seg">{['all', 'active', 'disabled', 'rejected'].map((k) => <button key={k} aria-pressed={show === k} onClick={() => setShow(k)}>{code(k)}</button>)}</span>
      </div>
      <div className="scroll" style={{ maxHeight: 420 }}>
        <table className="data">
          <thead><tr><th>{t('Name')}</th><th>{t('Email')}</th><th>{t('Organisation')}</th><th>{t('Role')}</th><th>{t('Status')}</th><th>{t('Since')}</th><th /></tr></thead>
          <tbody>{rest.map((u) => (
            <tr key={u.id}>
              <td><b dir="auto">{u.display_name}</b>{u.id === me.id && <span className="muted small"> {t('(you)')}</span>}</td>
              <td className="small">{u.email}</td><td className="small" dir="auto">{u.organisation || '–'}</td>
              <td><select value={u.role} disabled={u.id === me.id} aria-label={t('Role for {name}', { name: u.display_name })}
                onChange={(e) => patch(u, { role: e.target.value })}>{['admin', 'journalist', 'viewer'].map((r) => <option key={r} value={r}>{code(r)}</option>)}</select></td>
              <td className="small">{code(u.status)}{u.approved_by && <span className="muted"> · {t('approved by {name}', { name: u.approved_by })}</span>}</td>
              <td className="small mono">{u.created_at.slice(0, 10)}</td>
              <td>{u.id !== me.id && (u.status === 'active'
                ? <button className="btn small ghost" onClick={() => patch(u, { status: 'disabled' })}>{t('Disable')}</button>
                : <button className="btn small" onClick={() => patch(u, { status: 'active' })}>{t('Re-enable')}</button>)}</td>
            </tr>))}</tbody>
        </table>
      </div>
    </section>
  )
}

function PendingRow({ u, onDecide }) {
  const [role, setRole] = useState('journalist')
  return (
    <li>
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div><b dir="auto">{u.display_name}</b> <span className="small muted">{u.email} · <span dir="auto">{u.organisation || t('no organisation given')}</span> · {t('requested {date}', { date: day(u.created_at.slice(0, 10)) })}</span>
          {u.note && <div className="small" dir="auto" style={{ marginTop: 4 }}>“{u.note}”</div>}</div>
        <div className="row">
          <select value={role} onChange={(e) => setRole(e.target.value)} aria-label={t('Role to grant')}>
            {['viewer', 'journalist', 'admin'].map((r) => <option key={r} value={r}>{code(r)}</option>)}</select>
          <button className="btn small primary" onClick={() => onDecide(u, { status: 'active', role })}>{t('Approve')}</button>
          <button className="btn small ghost" onClick={() => onDecide(u, { status: 'rejected' })}>{t('Reject')}</button>
        </div>
      </div>
    </li>
  )
}

function FeedbackCard() {
  const [rows, setRows] = useState([])
  const [filter, setFilter] = useState('new')
  const [drafts, setDrafts] = useState({})
  const load = () => api('/api/admin/feedback' + (filter === 'all' ? '' : `?status=${filter}`)).then(setRows)
  useEffect(() => { load() }, [filter])
  const save = async (f, body) => { await api(`/api/admin/feedback/${f.id}`, { method: 'PATCH', body }); setDrafts({ ...drafts, [f.id]: '' }); load() }
  return (
    <section className="card" style={{ marginTop: 16 }}>
      <div className="card-head">
        <div><h2>{t('Suggestions and questions')}</h2><p className="sub">{t('Left at the bottom of each page. Replies are shown to the person who wrote them.')}</p></div>
        <span className="seg">{['new', 'answered', 'planned', 'done', 'all'].map((k) => <button key={k} aria-pressed={filter === k} onClick={() => setFilter(k)}>{code(k)}</button>)}</span>
      </div>
      {rows.length === 0 ? <p className="small muted">{t('Nothing here.')}</p> : (
        <ul className="list">{rows.map((f) => (
          <li key={f.id}>
            <div className="small muted"><span className="pill">{code(f.kind)}</span> <span dir="auto">{f.user || t('deleted user')}</span> · {t('page')} <span className="mono">{f.page}</span> · {f.at.slice(0, 16).replace('T', ' ')} · {code(f.status)}</div>
            <div dir="auto" style={{ margin: '4px 0' }}>{f.body}</div>
            {f.reply && <div className="comment"><span className="meta">{t('Reply by {name}', { name: f.replied_by })}</span><div dir="auto">{f.reply}</div></div>}
            <div className="row">
              <input type="text" dir="auto" placeholder={t('Reply (shown to the author)')} value={drafts[f.id] || ''} style={{ flex: 1 }}
                onChange={(e) => setDrafts({ ...drafts, [f.id]: e.target.value })} />
              <button className="btn small" disabled={!(drafts[f.id] || '').trim()} onClick={() => save(f, { reply: drafts[f.id] })}>{t('Reply')}</button>
              <select value={f.status} onChange={(e) => save(f, { status: e.target.value })} aria-label={t('Status')}>
                {['new', 'answered', 'planned', 'done', 'closed'].map((st) => <option key={st} value={st}>{code(st)}</option>)}</select>
            </div>
          </li>))}</ul>)}
    </section>
  )
}

// The learned theme classifier: what is live, what it learned from, how well it does per theme,
// and every version with a way back (activating one re-scores all articles in the background).
const THEME_LABEL_TYPES = new Set(['theme_set', 'theme_relevance'])
// two decimals in the interface language's decimal mark, as fmtNum writes the counts next to them
const f2 = (x) => (x == null ? '–' : fmtNum(x, { minimumFractionDigits: 2, maximumFractionDigits: 2, useGrouping: false }))
const fmtN = (x) => (x == null ? '–' : fmtNum(Math.round(x)))
const prf = (m) => (m ? `${f2(m.p)} / ${f2(m.r)} / ${f2(m.f1)}` : '–')
const ci = (m) => (m?.p_ci ? t('precision {p}, recall {r} (95% interval)', { p: m.p_ci.map(f2).join('–'), r: m.r_ci.map(f2).join('–') }) : undefined)

function ModelsCard() {
  const { meta } = useApp()
  const [d, setD] = useState(null)
  const [msg, setMsg] = useState(null)
  const load = () => api('/api/admin/models').then(setD).catch((e) => setMsg(e.message))
  useEffect(() => { load() }, [])
  const activate = async (v) => {
    if (!window.confirm(t('Make {v} the live classifier? Every article is scored again with it in the background, which takes a few minutes. It stays live until you pick another version. New nightly versions stay switched off until then.', { v }))) return
    try {
      await api(`/api/admin/models/${encodeURIComponent(v)}/activate`, { method: 'POST' })
      setMsg(t('{v} is live. Articles are being scored again in the background.', { v })); load()
    } catch (e) { setMsg(e.message) }
  }
  const letNightly = async (v) => {
    try {
      await api(`/api/admin/models/${encodeURIComponent(v)}/activate?pin=false`, { method: 'POST' })
      setMsg(t('The nightly retrain can make a new version live again when it passes the check.')); load()
    } catch (e) { setMsg(e.message) }
  }
  const head = (
    <div><h2>{t('Theme classifier')}</h2>
      <p className="sub">{t('A model that sorts articles into themes next to the word lists. It learns from the labels people give on Contribute and with Label this, and retrains each night.')}</p></div>)
  if (!d) return <section className="card" style={{ marginTop: 16 }}>{head}{msg ? <p className="err">{msg}</p> : <div className="empty">{t('Loading…')}</div>}</section>
  const live = d.models.find((m) => m.active)
  const n = (origin) => d.labels.by_origin_and_type.filter((x) => x.origin === origin && THEME_LABEL_TYPES.has(x.label_type)).reduce((a, x) => a + x.n, 0)
  const lm = live?.metrics || {}
  const names = new Map(meta.themes.map((th) => [th.slug, pick(th, 'name')]))
  const use = (th) => (th.group !== 'gender' ? t('adds links')
    : th.gate ? t('can switch off word-list links')
      : t('word lists only until people label 100 articles with 10 about it (now {labelled} and {positives})', { labelled: fmtN(th.people_labelled), positives: fmtN(th.people_positives) }))
  return (
    <section className="card" style={{ marginTop: 16 }}>
      <div className="card-head">{head}</div>
      {msg && <div className="banner info">{msg}</div>}
      {!live ? <p>{t('No model is live. Until one is, the classifier changes no themes.')}</p> : (
        <p className="small">
          {t('Live:')} <b className="mono">{live.version}</b> · {t('trained {date} on {labels} labelled articles and {base} tagged by the word lists', {
            date: live.trained_on?.date || live.created_at.slice(0, 10), labels: fmtN(live.trained_on?.labels?.items), base: fmtN(live.trained_on?.base?.items),
          })} · {t('{n} theme links come from the model', { n: fmtN(d.links.model) })} · {t('{n} word-list links it switched off', { n: fmtN(d.links.vetoed) })}
        </p>)}
      {live && d.pinned && (
        <div className="row small" style={{ margin: '0 0 8px' }}>
          <span>{t('This version was made live by hand. The nightly retrain still checks new versions but leaves them switched off.')}</span>
          <button className="btn small" onClick={() => letNightly(live.version)}>{t('Let nightly updates take over')}</button>
        </div>)}
      <p className="small">{t('Theme labels:')} <b>{fmtN(n('explicit'))}</b> {t('from people and')} <b>{fmtN(n('silver'))}</b> {t('from our October review, which an AI made. Only people’s labels decide when the model may switch off gender matches.')}
        <span className="muted"> {t('People’s labels are counted here after the hourly update.')}</span></p>
      {live && (
        <>
          <h3>{t('How well it does, per theme')}</h3>
          <p className="small muted">{t('Precision / recall / F1 on {n} labelled articles, each scored by a version of the model that did not learn from it. Hover a figure for its range. The threshold is the model score an article needs for the theme.', { n: fmtN(lm.eval_items) })}</p>
          <div className="scroll" style={{ maxHeight: 'none' }}>
            <table className="data">
              <thead><tr><th>{t('Theme')}</th><th className="num">{t('Labelled')}</th><th className="num" title={t('Labelled as about this theme')}>{t('Yes')}</th><th className="num">{t('Threshold')}</th><th title={t('What we count now: the word lists and the model together')}>{t('Model')}</th>
                <th title={t('The word lists on their own')}>{t('Word lists alone')}</th><th title={t('The links we counted before this model: word lists and searches')}>{t('Before the model')}</th>
                <th>{t('Model use')}</th></tr></thead>
              <tbody>
                {d.themes.map((th) => {
                  const m = lm.themes?.[th.slug]
                  return (
                    <tr key={th.slug}>
                      <td>{names.get(th.slug) || th.slug}</td><td className="num">{fmtN(th.labelled)}</td><td className="num">{fmtN(th.positives)}</td>
                      <td className="num">{f2(th.threshold)}</td>
                      <td className="num" title={ci(m?.model)}><b>{prf(m?.model)}</b></td>
                      <td className="num" title={ci(m?.rules)}>{prf(m?.rules)}</td>
                      <td className="num" title={ci(m?.links_today)}>{prf(m?.links_today)}</td>
                      <td className="small">{use(th)}</td>
                    </tr>)
                })}
                {['non_gender', 'gender'].map((g) => lm.macro?.[g] && (
                  <tr key={g}><td><b>{g === 'gender' ? t('Average, gender themes') : t('Average, other themes')}</b></td><td /><td /><td />
                    <td className="num"><b>{prf(lm.macro[g].model)}</b></td><td className="num">{prf(lm.macro[g].rules)}</td>
                    <td className="num">{prf(lm.macro[g].links_today)}</td><td /></tr>))}
              </tbody>
            </table>
          </div>
        </>)}
      <h3>{t('Versions')}</h3>
      {d.models.length === 0 ? <p className="small muted">{t('No versions yet. The first one is trained offline and registered with the command line.')}</p> : (
        <div className="scroll" style={{ maxHeight: 320 }}>
          <table className="data">
            <thead><tr><th>{t('Version')}</th><th>{t('Trained')}</th><th className="num">{t('Labelled')}</th><th>{t('Average F1 (other / gender)')}</th><th>{t('Note')}</th><th /></tr></thead>
            <tbody>{d.models.map((m) => (
              <tr key={m.version}>
                <td className="mono">{m.version}</td>
                <td className="small mono">{m.created_at.slice(0, 16).replace('T', ' ')}</td>
                <td className="num">{fmtN(m.trained_on?.labels?.items)}</td>
                <td className="num">{f2(m.metrics?.macro?.non_gender?.model?.f1)} / {f2(m.metrics?.macro?.gender?.model?.f1)}</td>
                <td className="small muted" dir="auto" style={{ maxWidth: 360 }}>{m.note}</td>
                <td>{m.active ? <span className="pill ok">{m.pinned ? t('live, by hand') : t('live')}</span>
                  : m.file === false ? <span className="small muted" title={t('Old nightly versions lose their file to save space')}>{t('no file')}</span>
                    : <button className="btn small" onClick={() => activate(m.version)}>{t('Activate')}</button>}</td>
              </tr>))}</tbody>
          </table>
        </div>)}
    </section>
  )
}

// "How the numbers work": every calculation in plain words. Collapsed by default.
function MethodsCard() {
  const [open, setOpen] = useState(false)
  const [md, setMd] = useState(null)
  useEffect(() => { if (open && md == null) api('/api/admin/methods').then((r) => setMd(r.markdown)) }, [open])
  return (
    <section className="card" style={{ marginTop: 16 }}>
      <div className="card-head">
        <div><h2>{t('How the numbers work')}</h2>
          <p className="sub">{t('How every figure in Desert Watch is worked out, and where it can mislead you.')}</p></div>
        <button className="btn small" aria-expanded={open} onClick={() => setOpen(!open)}>{open ? t('Hide') : t('Show')}</button>
      </div>
      {open && (md == null ? <div className="empty">{t('Loading…')}</div> : <div className="prose"><Markdown text={md.replace(/^# .*\n/, '')} /></div>)}
    </section>
  )
}
