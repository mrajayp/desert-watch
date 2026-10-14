import { useEffect, useState } from 'react'
import { api } from '../api'
import { useApp } from '../App'
import SourceHealth from '../components/SourceHealth'

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
