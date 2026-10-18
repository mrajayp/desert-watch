// Admin card for the AI answers audit: runs and costs against the weekly cap, a dry-run plan and a
// manual run, a per-answer drill-down (the assistant's own search queries and the searched and cited
// URLs with titles, which can carry private names, so they are shown here only) and the domains the
// assistants used that are not in the outlet register.
// Runs have an origin: api (the automatic developer-API run, the only one that costs money and counts
// against the cap), panel (links team members logged from the apps on their phones, one run per app and
// week) and browser (supervised browser sessions from London). Panel and browser entries show their
// links and never who logged them; an admin can delete one (DELETE /api/ai-panel/entries/{id}).
import { Fragment, useEffect, useState } from 'react'
import { api, qs } from '../api'
import { useApp } from '../App'
import { fmtDate, fmtNum, isAr, N_, pick, t, tn } from '../i18n'

// brand names stay as they are in both languages
const ASSISTANT = { anthropic: 'Claude', openai: 'ChatGPT', perplexity: 'Perplexity' } // i18n-ok: brand names
const ORIGIN = { api: N_('developer API'), panel: N_('team, apps'), browser: N_('browser session') }
const ASKED_IN = { LY: N_('from {country}'), other: N_('from elsewhere'), London: N_('from London') }
// codes from the API, shown in the interface language; unknown codes as they are
const RUN_STATUS = {
  running: N_('running'), ok: N_('ok'), partial: N_('partial'), error: N_('error'), awaiting_key: N_('awaiting key'),
  over_budget: N_('over budget'), disabled: N_('switched off'),
}
const ANSWER_STATUS = {
  ok: N_('ok'), no_search: N_('answered without searching'), refused: N_('refused'), rate_limited: N_('rate limited'),
  error: N_('error'), over_budget: N_('over budget'), no_sources: N_('no sources shown'),
}
const LANG = { ar: N_('Arabic'), en: N_('English'), und: N_('language unclear') }
const MATCH = { path: N_('matched by path'), exact: N_('matched by host'), parent: N_('matched by parent domain'), social: N_('matched social account') }
// why the plan leaves an assistant out (runner._blocking, run_week)
const SKIP = {
  awaiting_key: N_('waiting for an API key'), disabled: N_('switched off'), already_run: N_('already ran this week'),
  running: N_('running now'), unknown_provider: N_('not an assistant this audit knows'), no_questions: N_('no questions in the country config'),
}
const code = (table, k, vars) => (table[k] ? t(table[k], vars) : k)
const who = (k) => ASSISTANT[k] || k
const originOf = (r) => r.origin || 'api'
// an automatic run is named by its assistant, a logged one by its app (the API sends the app's label)
const runName = (r) => (originOf(r) === 'api' ? who(r.provider) : r.label || r.provider)
// US dollars with 2 decimals: $0.41 in English, 0.41 دولار in Arabic (Intl's Arabic currency form
// comes out as "US$ 0.41" mirrored inside right-to-left text)
const usd = (x) => (x == null ? '–' : t('${amount}', { amount: fmtNum(x, { minimumFractionDigits: 2, maximumFractionDigits: 2, useGrouping: false }) }))
const when = (s) => (s ? fmtDate(s, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }) : '–')
const comma = () => (isAr() ? '، ' : ', ')
// only web links are clickable: a search result could carry any scheme
const webUrl = (u) => (/^https?:\/\//i.test(u || '') ? u : null)

export default function AiAuditAdmin() {
  const [d, setD] = useState(null)
  const [err, setErr] = useState(null)
  const [domains, setDomains] = useState(null)
  const [opts, setOpts] = useState({ provider: null, force: false })
  const [plan, setPlan] = useState(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState(null)
  const [open, setOpen] = useState(null) // the run whose answers are shown
  const [domOrigin, setDomOrigin] = useState('api') // unknown domains are listed for one origin at a time
  const loadDomains = () => api('/api/admin/ai-audit/unknown-domains' + qs({ weeks: 12, origin: domOrigin })).then(setDomains).catch(() => setDomains([]))
  const load = () => {
    api('/api/admin/ai-audit/runs').then((r) => { setD(r); setErr(null) }).catch((e) => setErr(e.message))
    loadDomains()
  }
  useEffect(() => { load() }, [])
  useEffect(() => { setDomains(null); loadDomains() }, [domOrigin])
  const choose = (patch) => { setOpts({ ...opts, ...patch }); setPlan(null) }
  const planRun = async () => {
    setBusy(true); setMsg(null)
    try { setPlan(await api('/api/admin/ai-audit/run', { method: 'POST', body: { ...opts, dry_run: true } })) } catch (e) { setMsg(e.message) } finally { setBusy(false) }
  }
  const runNow = async () => {
    if (!plan?.planned?.length) return
    if (!window.confirm(t('Run the AI answers audit now? Planned answers: {n}. Estimated cost {cost}. Spent this week: {spent} of the {cap} cap. The run stops before it would pass the cap.', {
      n: plan.planned.length, cost: usd(plan.estimated_usd), spent: usd(plan.spent_this_week_usd), cap: usd(plan.cap_usd),
    }))) return
    setBusy(true); setMsg(null)
    try {
      await api('/api/admin/ai-audit/run', { method: 'POST', body: { ...opts, dry_run: false } })
      setPlan(null); setMsg(t('Started. Answers are asked one at a time and take a few minutes. Refresh to see them.'))
      setTimeout(load, 20000)
    } catch (e) { setMsg(e.message) } finally { setBusy(false) }
  }
  const byProvider = (plan?.planned || []).reduce((m, p) => { (m[p.provider] = m[p.provider] || []).push(p); return m }, {})
  // fits_cap: how many planned answers fit under the cap, in the order they are asked
  const fits = plan ? (plan.fits_cap ?? (plan.estimated_usd + plan.spent_this_week_usd > plan.cap_usd ? 0 : plan.planned.length)) : 0
  const over = plan && fits < plan.planned.length

  return (
    <section className="card" style={{ marginTop: 16 }}>
      <div className="card-head">
        <div><h2>{t('AI answers audit')}</h2>
          <p className="sub">{t('Each week the same questions go to Claude, ChatGPT and Perplexity through their developer services, in Arabic and in English, with web search on. Team members can also log the links the AI apps on their phones showed, and an admin can log a supervised browser session. The three origins are listed and counted apart, and only the automatic runs cost money. The search queries, URLs and titles below are shown on this page only, because they can carry private names. Everyone else sees counts per outlet and domain, and only once the audit is opened to the team.')}</p></div>
        <button className="btn small" onClick={load}>{t('Refresh')}</button>
      </div>
      {err && <p className="err">{err}</p>}
      {msg && <div className="banner info">{msg}</div>}

      {d && (
        <div className="row small" style={{ marginBottom: 10 }}>
          <span>{t('This week (from {week}): {spent} of the {cap} cap', { week: fmtDate(d.week_start), spent: usd(d.week_cost_usd), cap: usd(d.cap_usd) })}</span>
          <meter min={0} max={d.cap_usd || 1} value={Math.min(d.week_cost_usd || 0, d.cap_usd || 1)} high={(d.cap_usd || 1) * 0.8} optimum={0}
            aria-label={t('Spent this week against the cap')} style={{ width: 120 }} />
          <span className="muted">{t('Year to date: {ytd}', { ytd: usd(d.ytd_cost_usd) })}</span>
        </div>)}

      <div className="row" style={{ marginBottom: 10 }}>
        <select value={opts.provider || ''} onChange={(e) => choose({ provider: e.target.value || null })} aria-label={t('Assistant')}>
          <option value="">{t('All assistants')}</option>
          <option value="anthropic">{ASSISTANT.anthropic}</option>
          <option value="openai">{ASSISTANT.openai}</option>
          <option value="perplexity">{ASSISTANT.perplexity}</option>
        </select>
        <label className="small row"><input type="checkbox" checked={opts.force} onChange={(e) => choose({ force: e.target.checked })} />{t('Run again even if it already ran this week')}</label>
        <button className="btn" disabled={busy} onClick={planRun}>{t('Plan this week’s run')}</button>
      </div>

      {plan && (
        <div className="banner info">
          <p className="small" style={{ marginTop: 0 }}>{t('Planned answers: {n}. Estimated cost {cost}. Spent this week {spent}, weekly cap {cap}.', {
            n: plan.planned.length, cost: usd(plan.estimated_usd), spent: usd(plan.spent_this_week_usd), cap: usd(plan.cap_usd) })}</p>
          {over && <p className="small err">{t('Only {fits} of the {n} planned answers fit under the cap. The run stops there and records the rest as over budget.', { fits, n: plan.planned.length })}</p>}
          {Object.entries(byProvider).map(([k, rows]) => (
            <div key={k} className="small" style={{ marginBottom: 4 }}>
              <b>{who(k)}</b>: {tn(rows.length, '{n} answer', '{n} answers')} · <span className="mono" dir="ltr">{[...new Set(rows.map((r) => r.question_key))].join(', ')}</span>
            </div>))}
          {(plan.skipped || []).length > 0 && (
            <div className="small muted">{t('Skipped: {list}', { list: plan.skipped.map((s) => (s.provider ? `${who(s.provider)} (${code(SKIP, s.reason)})` : code(SKIP, s.reason))).join(comma()) })}</div>)}
          <div className="row" style={{ marginTop: 8 }}>
            <button className="btn primary" disabled={busy || !plan.planned.length} onClick={runNow}>{t('Run now')}</button>
            <button className="btn ghost" onClick={() => setPlan(null)}>{t('Cancel')}</button>
          </div>
        </div>)}

      <h3>{t('Runs')}</h3>
      {!d ? (!err && <div className="empty">{t('Loading…')}</div>) : d.runs.length === 0 ? <p className="small muted">{t('No runs yet. The audit runs every Monday at 04:20 UTC, or from the button above.')}</p> : (
        <div className="scroll" style={{ maxHeight: 640 }}>
          <table className="data">
            <thead><tr><th>{t('Week')}</th><th>{t('Origin')}</th><th>{t('Assistant or app')}</th><th>{t('Model')}</th><th>{t('Status')}</th><th className="num">{t('Answers')}</th><th className="num">{t('Cost')}</th><th /></tr></thead>
            <tbody>{d.runs.map((r) => (
              <Fragment key={r.id}>
                <tr>
                  <td className="small">{fmtDate(r.week_start)}{r.forced && <> <span className="pill">{t('forced')}</span></>}</td>
                  <td className="small">{code(ORIGIN, originOf(r))}</td>
                  <td dir="auto">{runName(r)}</td>
                  <td className="mono small" dir="ltr">{r.model || '–'}</td>
                  <td className="small">{code(RUN_STATUS, r.status)}
                    {r.error && <div className="muted" dir="auto" style={{ maxWidth: 420, whiteSpace: 'pre-wrap' }}>{r.error}</div>}</td>
                  <td className="num">{fmtNum(r.answers)}{r.over_budget > 0 && <div className="small muted">{t('{n} over budget', { n: fmtNum(r.over_budget) })}</div>}
                    {originOf(r) !== 'api' && r.no_sources > 0 && <div className="small muted">{t('no sources shown: {n}', { n: fmtNum(r.no_sources) })}</div>}</td>
                  <td className="num">{originOf(r) === 'api' ? usd(r.cost_usd) : <span className="muted" title={t('Not counted against the cap')}>–</span>}</td>
                  <td><button className="btn small" aria-expanded={open === r.id} onClick={() => setOpen(open === r.id ? null : r.id)}>{open === r.id ? t('Hide answers') : t('Answers')}</button></td>
                </tr>
                {open === r.id && <tr><td colSpan={8}><RunAnswers run={r} /></td></tr>}
              </Fragment>))}
            </tbody>
          </table>
        </div>)}

      <h3>{t('Domains not in the register (12 weeks)')}</h3>
      <p className="small muted" style={{ marginTop: 0 }}>{t('Domains in the answers, searched or cited, that match no outlet, for one origin at a time. They are candidates for the register: nothing is added on its own. Libyan .ly domains are marked.')}</p>
      <span className="seg" role="group" aria-label={t('Origin')} style={{ marginBottom: 8, flexWrap: 'wrap' }}>
        {Object.keys(ORIGIN).map((k) => <button key={k} aria-pressed={domOrigin === k} onClick={() => setDomOrigin(k)}>{t(ORIGIN[k])}</button>)}
      </span>
      {!domains ? <div className="empty">{t('Loading…')}</div> : domains.length === 0 ? <p className="small muted">{t('None.')}</p> : (
        <div className="scroll" style={{ maxHeight: 320 }}>
          <table className="data">
            <thead><tr><th>{t('Domain')}</th><th className="num">{t('Cited')}</th>{domOrigin === 'api' && <th className="num" title={t('Times it appeared in search results')}>{t('Searched')}</th>}</tr></thead>
            <tbody>{domains.map((x) => (
              <tr key={x.domain}>
                <td><span dir="ltr">{x.domain}</span>{x.ly && <> <span className="pill flag">{'.ly'}</span></>}</td>
                <td className="num">{fmtNum(x.cited)}</td>{domOrigin === 'api' && <td className="num">{fmtNum(x.searched)}</td>}
              </tr>))}</tbody>
          </table>
        </div>)}
    </section>
  )
}

// one run's answers: the question, the assistant's own searches, and every searched and cited link
function RunAnswers({ run }) {
  const { meta } = useApp()
  const [rows, setRows] = useState(null)
  const [err, setErr] = useState(null)
  const load = () => api('/api/admin/ai-audit/answers' + qs({ run_id: run.id })).then(setRows).catch((e) => setErr(e.message))
  useEffect(() => { load() }, [run.id])
  const logged = originOf(run) !== 'api'
  const remove = async (a) => {
    if (!window.confirm(t('Delete this entry? Its links are taken out of the audit.'))) return
    try { await api(`/api/ai-panel/entries/${a.id}`, { method: 'DELETE' }); load() } catch (e) { setErr(e.message) }
  }
  if (logged) {
    const country = pick(meta?.country, 'name')
    const browser = originOf(run) === 'browser'
    return (
      <div style={{ padding: '4px 0' }}>
        <p className="small muted" style={{ marginTop: 0 }}>{browser
          ? t('A supervised browser session from London, in a signed-in account. Only the source links were logged. Not counted against the cap.')
          : t('Logged by team members in the apps on their own phones. Only the source links were logged. Not counted against the cap.')}</p>
        {err && <p className="err">{err}</p>}
        {!rows ? (!err && <div className="empty">{t('Loading…')}</div>) : rows.length === 0 ? <p className="small muted">{t('No answers recorded for this run.')}</p> : (
          rows.map((a) => {
            const links = a.cited || []
            const matched = links.filter((x) => x.outlet_id != null).length
            return (
              <details key={a.id} style={{ borderTop: '1px solid var(--grid)', padding: '6px 0' }}>
                <summary className="small" style={{ cursor: 'pointer' }}>
                  <span className="mono">{a.question_key}</span> · {code(LANG, a.lang)} · {code(ANSWER_STATUS, a.status)}
                  {a.asked_in && <> · {code(ASKED_IN, a.asked_in, { country })}</>}
                  {' · '}{t('{n} links, {matched} matched to an outlet', { n: fmtNum(links.length), matched: fmtNum(matched) })}
                  {a.created_at && <> · {when(a.created_at)}</>}
                </summary>
                <div style={{ paddingInlineStart: 14 }}>
                  {a.question && <p dir="auto" style={{ margin: '6px 0' }}>{a.question}{a.question_changed && <> <span className="pill">{t('the wording has changed since')}</span></>}</p>}
                  <p className="small muted" style={{ margin: '2px 0 6px' }}>{browser ? t('Logged in a supervised browser session') : a.author || t('Logged by a team member')}
                    {a.mine && <> <span className="pill">{t('your entry')}</span></>}</p>
                  <div className="small"><b>{t('Links ({n})', { n: links.length })}</b></div>
                  <Links rows={links} />
                  <button className="btn small ghost" onClick={() => remove(a)}>{t('Delete entry')}</button>
                </div>
              </details>)
          }))}
      </div>
    )
  }
  const s = run.settings || {}
  // the location sent with the questions; a list when the provider refused the first one and got a second
  const place = (o) => Object.entries(o || {}).map(([k, v]) => `${k}: ${v}`).join(', ')
  const loc = Array.isArray(s.location_sent) ? s.location_sent.map(place).join(' / ') : place(s.location_sent)
  return (
    <div style={{ padding: '4px 0' }}>
      <p className="small muted" style={{ marginTop: 0 }}>
        {t('Location sent:')} <span className="mono" dir="ltr">{loc || '–'}</span>
        {s.max_searches != null && <> · {tn(s.max_searches, 'up to {n} search per answer', 'up to {n} searches per answer')}</>}
        {s.fly_region && <> · {t('server region {region}', { region: s.fly_region })}</>}
        {s.date_line != null && <> · {s.date_line ? t('date line sent') : t('no date line')}</>}
        {' · '}{t('{from} to {to} UTC', { from: when(run.started_at), to: when(run.finished_at) })}
      </p>
      {err && <p className="err">{err}</p>}
      {!rows ? (!err && <div className="empty">{t('Loading…')}</div>) : rows.length === 0 ? <p className="small muted">{t('No answers recorded for this run.')}</p> : (
        rows.map((a) => (
          <details key={a.id} style={{ borderTop: '1px solid var(--grid)', padding: '6px 0' }}>
            <summary className="small" style={{ cursor: 'pointer' }}>
              <span className="mono">{a.question_key}</span> · {code(LANG, a.lang)} · {code(ANSWER_STATUS, a.status)}
              {' · '}{t('{searched} searched, {cited} cited', { searched: fmtNum(a.n_searched), cited: fmtNum(a.n_cited) })} · {usd(a.cost_usd)}
            </summary>
            <div style={{ paddingInlineStart: 14 }}>
              {a.question && <p dir="auto" style={{ margin: '6px 0' }}>{a.question}{a.question_changed && <> <span className="pill">{t('the wording has changed since')}</span></>}</p>}
              <div className="small"><b>{t('Its own search queries')}</b></div>
              {(a.queries || []).length === 0 ? <p className="small muted" style={{ margin: '2px 0 6px' }}>{t('None.')}</p> : (
                <ul className="small" style={{ margin: '2px 0 6px', paddingInlineStart: 18 }}>{a.queries.map((q, i) => <li key={i} dir="auto">{q}</li>)}</ul>)}
              <div className="small"><b>{t('Cited ({n})', { n: (a.cited || []).length })}</b></div>
              <Links rows={a.cited} cited />
              <div className="small"><b>{t('Searched ({n})', { n: (a.searched || []).length })}</b></div>
              <Links rows={a.searched} />
            </div>
          </details>)))}
    </div>
  )
}

function Links({ rows, cited = false }) {
  if (!rows?.length) return <p className="small muted" style={{ margin: '2px 0 6px' }}>{t('None.')}</p>
  return (
    <ol className="small" style={{ margin: '2px 0 8px', paddingInlineStart: 22 }}>{rows.map((x, i) => {
      const href = webUrl(x.url)
      const text = x.title || x.url
      return (
        <li key={i} style={{ marginBottom: 4 }}>
          {href ? <a href={href} target="_blank" rel="noreferrer noopener" dir="auto" style={{ wordBreak: x.title ? undefined : 'break-all' }}>{text}</a>
            : <span dir="auto" style={{ wordBreak: 'break-all' }}>{text}</span>}
          {cited && x.citations > 0 && <span className="muted"> · {tn(x.citations, '{n} citation', '{n} citations')}</span>}
          <div className="muted">
            <span dir="ltr">{x.domain}</span>
            {' · '}{x.outlet_id != null ? <><span dir="auto">{x.outlet_name}</span> ({code(MATCH, x.match)})</> : <span className="pill">{t('not in the register')}</span>}
            {x.lang && <> · {code(LANG, x.lang)}</>}
          </div>
        </li>)
    })}</ol>)
}
