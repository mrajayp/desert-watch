import { useEffect, useState } from 'react'
import { api } from '../api'
import { useApp } from '../App'
import SourceHealth from '../components/SourceHealth'
import { Markdown } from './Digest'

const split = (s) => s.split(/\n|,|،/).map((x) => x.trim()).filter(Boolean)

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
  const startEdit = (t) => { setPreview(null); setEdit(t ? { ...t, en: t.en_terms.join('\n'), ar: t.ar_terms.join('\n'), ex: t.exclude.join('\n') } : { id: null, name_en: '', name_ar: '', en: '', ar: '', ex: '', active: true }) }
  const body = () => ({ name_en: edit.name_en, name_ar: edit.name_ar, en_terms: split(edit.en), ar_terms: split(edit.ar), exclude: split(edit.ex), active: edit.active,
    acled_event_types: edit.acled_event_types || [], reliefweb_themes: edit.reliefweb_themes || [] })
  const runPreview = async () => setPreview(await api('/api/themes/preview', { method: 'POST', body: body() }))
  const saveTheme = async () => {
    await api(edit.id ? `/api/themes/${edit.id}` : '/api/themes', { method: edit.id ? 'PUT' : 'POST', body: body() })
    setMsg('Saved. Articles are being re-tagged and scores recomputed in the background.'); setEdit(null); load(); setTimeout(refresh, 4000)
  }
  const sendInvite = async (e) => {
    e.preventDefault()
    const r = await api('/api/admin/invites', { method: 'POST', body: invite })
    setInviteLink(location.origin + r.invite_path); setInvite({ email: '', role: 'journalist' })
  }
  const review = async (id, accept) => { await api(`/api/admin/suggestions/${id}`, { method: 'POST', body: { accept } }); load() }
  const run = async (job) => { await api(`/api/admin/run/${job}`, { method: 'POST' }); setMsg(`Queued ${job}. Refresh in a minute.`) }

  return (
    <main className="page">
      {msg && <div className="banner info">{msg}</div>}
      <div className="grid halves">
        <section className="card">
          <div className="card-head"><h2>Themes</h2><button className="btn small" onClick={() => startEdit(null)}>+ New theme</button></div>
          <p className="sub">Editing a theme bumps its version and re-tags all articles. Arabic terms only apply to RSS and Google News (GDELT can’t search Arabic script).</p>
          <ul className="list">{themes.map((t) => (
            <li key={t.id} className="row" style={{ justifyContent: 'space-between' }}>
              <span><b>{t.name_en}</b> <span className="ar" dir="rtl">{t.name_ar}</span> <span className="muted small">v{t.version} · {t.en_terms.length} EN / {t.ar_terms.length} AR terms{!t.active && ' · inactive'}</span></span>
              <button className="btn small" onClick={() => startEdit(t)}>Edit</button></li>))}</ul>
          {edit && (
            <div className="form" style={{ marginTop: 12 }}>
              <div className="row"><label style={{ flex: 1 }}>Name (EN)<input type="text" value={edit.name_en} onChange={(e) => setEdit({ ...edit, name_en: e.target.value })} /></label>
                <label style={{ flex: 1 }}>Name (AR)<input type="text" dir="rtl" value={edit.name_ar} onChange={(e) => setEdit({ ...edit, name_ar: e.target.value })} /></label></div>
              <div className="grid halves">
                <label>English terms (one per line)<textarea rows={7} value={edit.en} onChange={(e) => setEdit({ ...edit, en: e.target.value })} /></label>
                <label>Arabic terms<textarea rows={7} dir="rtl" value={edit.ar} onChange={(e) => setEdit({ ...edit, ar: e.target.value })} /></label>
              </div>
              <label>Exclusions (veto a match)<textarea rows={2} value={edit.ex} onChange={(e) => setEdit({ ...edit, ex: e.target.value })} /></label>
              <label className="row"><input type="checkbox" checked={edit.active} onChange={(e) => setEdit({ ...edit, active: e.target.checked })} />Active</label>
              <div className="row"><button className="btn" onClick={runPreview}>Preview matches (30 days)</button><span className="spacer" />
                <button className="btn ghost" onClick={() => setEdit(null)}>Cancel</button><button className="btn primary" disabled={!edit.name_en} onClick={saveTheme}>Save</button></div>
              {preview && (
                <div>
                  <p className="small">Matches {preview.matched} of {preview.scanned} recent articles. Top terms: {preview.top_terms.slice(0, 8).map(([t, n]) => `${t} (${n})`).join(', ')}</p>
                  <ul className="list small scroll" style={{ maxHeight: 260 }}>{preview.samples.map((s) => (
                    <li key={s.id}><span dir="auto">{s.title}</span> <span className="muted">[{s.hits.join(', ')}]</span>{!s.relevant && <span className="pill flag">marked junk</span>}</li>))}</ul>
                  <p className="small muted">Check precision before saving: if fewer than ~8 in 10 samples are on-topic, tighten terms or add exclusions.</p>
                </div>)}
            </div>)}
        </section>
        <section className="card">
          <h2>Invite a journalist</h2>
          <form className="row" onSubmit={sendInvite}>
            <input type="email" required placeholder="email" value={invite.email} onChange={(e) => setInvite({ ...invite, email: e.target.value })} />
            <select value={invite.role} onChange={(e) => setInvite({ ...invite, role: e.target.value })}><option value="journalist">Journalist</option><option value="admin">Admin</option></select>
            <button className="btn primary">Create invite</button>
          </form>
          {inviteLink && <p className="small">Send this link privately (valid 7 days): <code style={{ wordBreak: 'break-all' }}>{inviteLink}</code></p>}

          <h2 style={{ marginTop: 20 }}>Suggestions queue ({sugs.length})</h2>
          {sugs.length === 0 ? <p className="muted small">Nothing pending.</p> : (
            <ul className="list small">{sugs.map((g) => (
              <li key={g.id}><b>{g.kind}</b> by {g.user || g.origin} · <span className="mono">{JSON.stringify(g.payload)}</span>
                <div className="row"><button className="btn small" onClick={() => review(g.id, true)}>Accept</button><button className="btn small ghost" onClick={() => review(g.id, false)}>Reject</button></div></li>))}</ul>)}

          <h2 style={{ marginTop: 20 }}>Learning</h2>
          {learning && (
            <div className="small">
              <p>Labels: {Object.entries(learning.labels).map(([k, v]) => `${k} ${v}`).join(' · ') || 'none yet'} ({learning.by_origin.explicit || 0} explicit, {learning.by_origin.implicit || 0} implicit)</p>
              <p>Behaviour events: {Object.entries(learning.events).map(([k, v]) => `${k} ${v}`).join(' · ') || 'none yet'}</p>
              <p>Vote agreement: {learning.vote_agreement.unanimous} of {learning.vote_agreement.gaps_with_multiple_votes} gaps with 2+ votes are unanimous.</p>
              {learning.rule_confirmation && Object.keys(learning.rule_confirmation).length > 0 && (
                <>
                  <p style={{ marginBottom: 4 }}><b>Precision proxy</b> — share of search results (last 28 days) whose theme the keyword rules confirm. Low = the search returns loosely related items, or the rules miss vocabulary:</p>
                  <table className="data"><thead><tr><th>Theme / language</th><th className="num">Items</th><th className="num">Confirmed</th></tr></thead>
                    <tbody>{Object.entries(learning.rule_confirmation).map(([k, v]) => (
                      <tr key={k}><td>{k}</td><td className="num">{v.n}</td><td className="num">{Math.round(v.confirmed * 100)}%{v.confirmed < 0.5 && <span className="pill flag" style={{ marginLeft: 6 }}>review terms</span>}</td></tr>))}</tbody></table>
                </>)}
              <p className="muted">Models switch on at: {Object.entries(learning.thresholds).map(([k, v]) => `${k.replace(/_/g, ' ')} ≥ ${v}`).join('; ')}. Until then rankings are rule-based.</p>
            </div>)}
        </section>
      </div>
      <ModelsCard />
      <MethodsCard />
      <UsersCard />
      <FeedbackCard />
      <AlertsCard />
      <section className="card" style={{ marginTop: 16 }}>
        <div className="card-head"><h2>Data sources</h2>
          <div className="row">{['rss', 'galerts', 'gnews', 'digest', 'gdelt', 'gdelt_timeline', 'wikipedia', 'recompute'].map((j) => <button key={j} className="btn small" onClick={() => run(j)}>Run {j}</button>)}</div></div>
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
  const copy = (t) => navigator.clipboard?.writeText(t)
  return (
    <section className="card" style={{ marginTop: 16 }}>
      <div className="card-head">
        <div><h2>Google Alerts ({attached} of {data.alerts.length} connected)</h2>
          <p className="sub">Create each alert at google.com/alerts with: {Object.entries(data.settings).map(([k, v]) => `${k}: ${v}`).join(' · ')}. Then paste its RSS feed URL below. Alerts collect from the day they are created.</p></div>
        <input type="text" placeholder="Filter (e.g. district, sabha, :ar)" value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filter alerts" />
      </div>
      <div className="scroll" style={{ maxHeight: 360 }}>
        <table className="data">
          <thead><tr><th>Key</th><th>Label</th><th>Query</th><th>Feed</th></tr></thead>
          <tbody>{shown.map((a) => (
            <tr key={a.key}>
              <td className="mono">{a.key}</td><td>{a.label}</td>
              <td><code dir="ltr" style={{ unicodeBidi: "isolate" }}>{a.query}</code> <button className="btn small ghost" onClick={() => copy(a.query)} title="Copy query">Copy</button></td>
              <td className="small">{a.feed_url ? (a.last_error ? <span className="err">error</span> : a.last_ok_at ? `ok · ${a.last_items} items` : 'connected') : <span className="muted">not connected</span>}</td>
            </tr>))}</tbody>
        </table>
      </div>
      <h3>Connect feeds</h3>
      <textarea rows={4} className="mono" placeholder={'district:sabha:ar https://www.google.com/alerts/feeds/…/…\ntheme:health:en https://www.google.com/alerts/feeds/…/…'} value={lines} onChange={(e) => setLines(e.target.value)} />
      <div className="row" style={{ marginTop: 6 }}>
        <button className="btn primary" disabled={!lines.trim()} onClick={save}>Connect</button>
        {result && <span className="small">{result.attached} connected{result.problems.length ? ` · problems: ${result.problems.join('; ')}` : ''}</span>}
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
  const ROLE_HELP = { admin: 'everything, incl. users & themes', journalist: 'vote, comment, add & correct', viewer: 'read-only' }
  return (
    <section className="card" style={{ marginTop: 16 }}>
      <h2>Users and access</h2>
      <p className="sub">People can request access from the sign-in page. Approve them with a role, or reject. Roles: {Object.entries(ROLE_HELP).map(([r, h]) => `${r} (${h})`).join(' · ')}.</p>
      {err && <p className="err">{err}</p>}
      <h3>Access requests ({pending.length})</h3>
      {pending.length === 0 ? <p className="small muted">No pending requests.</p> : (
        <ul className="list">{pending.map((u) => <PendingRow key={u.id} u={u} onDecide={patch} />)}</ul>)}
      <div className="row" style={{ justifyContent: 'space-between', marginTop: 12 }}>
        <h3 style={{ margin: 0 }}>All users ({users.length - pending.length})</h3>
        <span className="seg">{['all', 'active', 'disabled', 'rejected'].map((k) => <button key={k} aria-pressed={show === k} onClick={() => setShow(k)}>{k}</button>)}</span>
      </div>
      <div className="scroll" style={{ maxHeight: 420 }}>
        <table className="data">
          <thead><tr><th>Name</th><th>Email</th><th>Organisation</th><th>Role</th><th>Status</th><th>Since</th><th /></tr></thead>
          <tbody>{rest.map((u) => (
            <tr key={u.id}>
              <td><b>{u.display_name}</b>{u.id === me.id && <span className="muted small"> (you)</span>}</td>
              <td className="small">{u.email}</td><td className="small">{u.organisation || '–'}</td>
              <td><select value={u.role} disabled={u.id === me.id} aria-label={`Role for ${u.display_name}`}
                onChange={(e) => patch(u, { role: e.target.value })}>{['admin', 'journalist', 'viewer'].map((r) => <option key={r}>{r}</option>)}</select></td>
              <td className="small">{u.status}{u.approved_by && <span className="muted"> · approved by {u.approved_by}</span>}</td>
              <td className="small mono">{u.created_at.slice(0, 10)}</td>
              <td>{u.id !== me.id && (u.status === 'active'
                ? <button className="btn small ghost" onClick={() => patch(u, { status: 'disabled' })}>Disable</button>
                : <button className="btn small" onClick={() => patch(u, { status: 'active' })}>Re-enable</button>)}</td>
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
        <div><b>{u.display_name}</b> <span className="small muted">{u.email} · {u.organisation || 'no organisation given'} · requested {u.created_at.slice(0, 10)}</span>
          {u.note && <div className="small" dir="auto" style={{ marginTop: 4 }}>“{u.note}”</div>}</div>
        <div className="row">
          <select value={role} onChange={(e) => setRole(e.target.value)} aria-label="Role to grant">
            {['viewer', 'journalist', 'admin'].map((r) => <option key={r}>{r}</option>)}</select>
          <button className="btn small primary" onClick={() => onDecide(u, { status: 'active', role })}>Approve</button>
          <button className="btn small ghost" onClick={() => onDecide(u, { status: 'rejected' })}>Reject</button>
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
        <div><h2>Suggestions and questions</h2><p className="sub">Left at the bottom of each page. Replies are shown to the person who wrote them.</p></div>
        <span className="seg">{['new', 'answered', 'planned', 'done', 'all'].map((k) => <button key={k} aria-pressed={filter === k} onClick={() => setFilter(k)}>{k}</button>)}</span>
      </div>
      {rows.length === 0 ? <p className="small muted">Nothing here.</p> : (
        <ul className="list">{rows.map((f) => (
          <li key={f.id}>
            <div className="small muted"><span className="pill">{f.kind}</span> {f.user || 'deleted user'} · page <span className="mono">{f.page}</span> · {f.at.slice(0, 16).replace('T', ' ')} · {f.status}</div>
            <div dir="auto" style={{ margin: '4px 0' }}>{f.body}</div>
            {f.reply && <div className="comment"><span className="meta">Reply by {f.replied_by}</span><div dir="auto">{f.reply}</div></div>}
            <div className="row">
              <input type="text" dir="auto" placeholder="Reply (shown to the author)" value={drafts[f.id] || ''} style={{ flex: 1 }}
                onChange={(e) => setDrafts({ ...drafts, [f.id]: e.target.value })} />
              <button className="btn small" disabled={!(drafts[f.id] || '').trim()} onClick={() => save(f, { reply: drafts[f.id] })}>Reply</button>
              <select value={f.status} onChange={(e) => save(f, { status: e.target.value })} aria-label="Status">
                {['new', 'answered', 'planned', 'done', 'closed'].map((st) => <option key={st}>{st}</option>)}</select>
            </div>
          </li>))}</ul>)}
    </section>
  )
}

// The learned theme classifier: what is live, what it learned from, how well it does per theme,
// and every version with a way back (activating one re-scores all articles in the background).
const THEME_LABEL_TYPES = new Set(['theme_set', 'theme_relevance'])
const f2 = (x) => (x == null ? '–' : x.toFixed(2))
const fmtN = (x) => (x == null ? '–' : Math.round(x).toLocaleString())
const prf = (m) => (m ? `${f2(m.p)} / ${f2(m.r)} / ${f2(m.f1)}` : '–')
const ci = (m) => (m?.p_ci ? `precision ${m.p_ci.map(f2).join('–')}, recall ${m.r_ci.map(f2).join('–')} (95% interval)` : undefined)

function ModelsCard() {
  const { meta } = useApp()
  const [d, setD] = useState(null)
  const [msg, setMsg] = useState(null)
  const load = () => api('/api/admin/models').then(setD).catch((e) => setMsg(e.message))
  useEffect(() => { load() }, [])
  const activate = async (v) => {
    if (!window.confirm(`Make ${v} the live classifier? Every article is scored again with it in the background, which takes a few minutes.`)) return
    try {
      await api(`/api/admin/models/${encodeURIComponent(v)}/activate`, { method: 'POST' })
      setMsg(`${v} is live. Articles are being scored again in the background.`); load()
    } catch (e) { setMsg(e.message) }
  }
  const head = (
    <div><h2>Theme classifier</h2>
      <p className="sub">A model that sorts articles into themes next to the word rules. It learns from the labels people give on Contribute and with Label this, and retrains each night.</p></div>)
  if (!d) return <section className="card" style={{ marginTop: 16 }}>{head}{msg ? <p className="err">{msg}</p> : <div className="empty">Loading…</div>}</section>
  const live = d.models.find((m) => m.active)
  const n = (origin) => d.labels.by_origin_and_type.filter((x) => x.origin === origin && THEME_LABEL_TYPES.has(x.label_type)).reduce((a, x) => a + x.n, 0)
  const lm = live?.metrics || {}
  const names = new Map(meta.themes.map((t) => [t.slug, t.name_en]))
  const use = (t, m) => (t.group !== 'gender' ? 'adds links' : t.gate ? 'can turn off rule links' : m?.blended === false ? 'rules only (too few labels)' : 'rules only')
  return (
    <section className="card" style={{ marginTop: 16 }}>
      <div className="card-head">{head}</div>
      {msg && <div className="banner info">{msg}</div>}
      {!live ? <p>No model is live. Until one is, the classifier changes no themes.</p> : (
        <p className="small">
          Live: <b className="mono">{live.version}</b> · trained {live.trained_on?.date || live.created_at.slice(0, 10)} on {fmtN(live.trained_on?.labels?.items)} labelled
          and {fmtN(live.trained_on?.base?.items)} rule-tagged articles · {fmtN(d.links.model)} theme links come from the model · {fmtN(d.links.vetoed)} rule links it turned off
        </p>)}
      <p className="small">Theme labels: <b>{fmtN(n('explicit'))}</b> from people and <b>{fmtN(n('silver'))}</b> silver labels from our review.
        <span className="muted"> People’s labels are counted here after the hourly update.</span></p>
      {live && (
        <>
          <h3>How well it does, per theme</h3>
          <p className="small muted">Precision / recall / F1 on {fmtN(lm.eval_items)} labelled articles, each scored by a version of the model that did not learn from it. Hover a figure for its range.
            The threshold is the model score an article needs for the theme.</p>
          <div className="scroll" style={{ maxHeight: 'none' }}>
            <table className="data">
              <thead><tr><th>Theme</th><th className="num">Labelled</th><th className="num" title="Labelled as about this theme">Yes</th><th className="num">Threshold</th><th title="What we count now: the word rules and the model together">Model</th>
                <th title="The word rules on their own">Rules alone</th><th title="The links we counted before this model: word rules and searches">Before the model</th>
                <th>Model use</th></tr></thead>
              <tbody>
                {d.themes.map((t) => {
                  const m = lm.themes?.[t.slug]
                  return (
                    <tr key={t.slug}>
                      <td>{names.get(t.slug) || t.slug}</td><td className="num">{fmtN(t.labelled)}</td><td className="num">{fmtN(t.positives)}</td>
                      <td className="num">{f2(t.threshold)}</td>
                      <td className="num" title={ci(m?.model)}><b>{prf(m?.model)}</b></td>
                      <td className="num" title={ci(m?.rules)}>{prf(m?.rules)}</td>
                      <td className="num" title={ci(m?.links_today)}>{prf(m?.links_today)}</td>
                      <td className="small">{use(t, m)}</td>
                    </tr>)
                })}
                {['non_gender', 'gender'].map((g) => lm.macro?.[g] && (
                  <tr key={g}><td><b>Average, {g === 'gender' ? 'gender themes' : 'other themes'}</b></td><td /><td /><td />
                    <td className="num"><b>{prf(lm.macro[g].model)}</b></td><td className="num">{prf(lm.macro[g].rules)}</td>
                    <td className="num">{prf(lm.macro[g].links_today)}</td><td /></tr>))}
              </tbody>
            </table>
          </div>
        </>)}
      <h3>Versions</h3>
      {d.models.length === 0 ? <p className="small muted">No versions yet. The first one is trained offline and registered with the command line.</p> : (
        <div className="scroll" style={{ maxHeight: 320 }}>
          <table className="data">
            <thead><tr><th>Version</th><th>Trained</th><th className="num">Labelled</th><th>Average F1 (other / gender)</th><th>Note</th><th /></tr></thead>
            <tbody>{d.models.map((m) => (
              <tr key={m.version}>
                <td className="mono">{m.version}</td>
                <td className="small mono">{m.created_at.slice(0, 16).replace('T', ' ')}</td>
                <td className="num">{fmtN(m.trained_on?.labels?.items)}</td>
                <td className="num">{f2(m.metrics?.macro?.non_gender?.model?.f1)} / {f2(m.metrics?.macro?.gender?.model?.f1)}</td>
                <td className="small muted" style={{ maxWidth: 360 }}>{m.note}</td>
                <td>{m.active ? <span className="pill ok">live</span>
                  : <button className="btn small" onClick={() => activate(m.version)}>Activate</button>}</td>
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
        <div><h2>How the numbers work</h2>
          <p className="sub">How every figure in Desert Watch is worked out, and where it can mislead you.</p></div>
        <button className="btn small" aria-expanded={open} onClick={() => setOpen(!open)}>{open ? 'Hide' : 'Show'}</button>
      </div>
      {open && (md == null ? <div className="empty">Loading…</div> : <div className="prose"><Markdown text={md.replace(/^# .*\n/, '')} /></div>)}
    </section>
  )
}
