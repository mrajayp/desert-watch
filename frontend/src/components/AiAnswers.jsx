// AI answers audit (docs/research/ai_answers_audit_scope.md): which sources two AI assistants search
// and cite when they get the same fixed questions about the country each week, in Arabic and English,
// next to the mix of the coverage Desert Watch monitors. Counts are per assistant and never added
// up. Nothing here feeds a gap score. The API answers {"visible": false} to anyone who may not see
// the results (admins only until config/ai_audit.yaml says visible_to: team); the card then stays hidden.
import { useEffect, useState } from 'react'
import { api, qs } from '../api'
import { useApp } from '../App'
import { MixBar } from '../charts/Balance'
import { DIMENSIONS, categoryColor } from '../charts/scales'
import { fmtDate, fmtNum, N_, pick, t, tn } from '../i18n'

// brand names stay as they are in both languages
const ASSISTANT = { anthropic: 'Claude', openai: 'ChatGPT' } // i18n-ok: brand names
// each assistant's last run (a code from the API)
const STATUS = {
  ok: N_('last run complete'), partial: N_('last run partly complete'), over_budget: N_('last run stopped at the weekly cost cap'),
  error: N_('last run failed'), awaiting_key: N_('waiting for an API key'), disabled: N_('switched off'),
  never_run: N_('not run yet'), running: N_('running now'),
}
const SCOPES = ['libyan', 'diaspora', 'international', 'unknown_scope', 'unregistered']
const SCOPE_COLOR = {
  libyan: categoryColor('scope', 'libyan'), diaspora: categoryColor('scope', 'diaspora'), international: categoryColor('scope', 'international'),
  unknown_scope: 'var(--cat-unknown)', unregistered: 'var(--muted)',
}
// scope labels in the interface language (DIMENSIONS values are translated when read)
const scopeLabels = () => ({
  libyan: DIMENSIONS.scope.values.libyan, diaspora: DIMENSIONS.scope.values.diaspora, international: DIMENSIONS.scope.values.international,
  unknown_scope: DIMENSIONS.scope.values.unknown, unregistered: t('Not in the register'),
})
const parts = (o) => Object.fromEntries(SCOPES.map((k) => [k, Number(o?.[k]) || 0]))
const total = (o) => Object.values(o || {}).reduce((a, v) => a + (Number(v) || 0), 0)
// a median can be a half (7.5)
const dec = (v) => (v == null ? '–' : fmtNum(v, { maximumFractionDigits: 1 }))
const spread = (r) => (r && r.median != null ? t('{median} (range {min}–{max})', { median: dec(r.median), min: dec(r.min), max: dec(r.max) }) : '–')
const pct = (n, of) => (of ? Math.round((n / of) * 100) : 0)
// a host name the API sends; anything else is not linked
const siteUrl = (d) => (/^[a-z0-9.-]+\.[a-z]{2,}$/i.test(d || '') ? `https://${d}` : null)
const NEVER_SHOWN = 40

export default function AiAnswers() {
  const { meta, openOutlet } = useApp()
  const [provider, setProvider] = useState('all')
  const [qlang, setQlang] = useState('all')
  const [weeks, setWeeks] = useState(4)
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const [allNever, setAllNever] = useState(false)
  useEffect(() => {
    const ac = new AbortController()
    api('/api/ai-audit/summary' + qs({ weeks, provider, lang: qlang }), { signal: ac.signal })
      .then((r) => { setData(r); setErr(null) })
      .catch((e) => {
        if (e.name === 'AbortError') return
        setData((d) => d || { visible: false })
        setErr(e.message)
      })
    return () => ac.abort()
  }, [weeks, provider, qlang])
  if (!data || !data.visible) return null

  const labels = scopeLabels()
  const providers = data.providers || []
  const status = data.status || {}
  const one = provider !== 'all'
  const never = data.never_cited || []
  const neverShown = allNever ? never : never.slice(0, NEVER_SHOWN)
  const appeared = neverShown.filter((r) => r.appeared_in_results)
  const unseen = neverShown.filter((r) => !r.appeared_in_results)
  const covTotal = total(data.coverage_scope)
  const chip = (r) => (
    <button key={r.outlet_id} className="chip" dir="auto" onClick={() => openOutlet(r.outlet_id)}
      title={`${r.domain || ''} · ${tn(r.articles_12w, '{n} article in 12 weeks', '{n} articles in 12 weeks')}`}>{r.name}</button>)

  return (
    <section className="card" style={{ marginTop: 16 }}>
      <div className="card-head">
        <div><h2>{t('What AI assistants cite')}</h2>
          <p className="sub">{t('Each week Claude and ChatGPT get the same set of questions about {country}, in Arabic and in English, with web search on. We count the sources they search and the sources they cite, per assistant.', { country: pick(meta?.country, 'name') })}</p></div>
        <div className="row">
          <span className="seg" role="group" aria-label={t('Assistant')}>
            {[['all', t('Both')], ['anthropic', ASSISTANT.anthropic], ['openai', ASSISTANT.openai]].map(([k, l]) =>
              <button key={k} aria-pressed={provider === k} onClick={() => setProvider(k)}>{l}</button>)}
          </span>
          <span className="seg" role="group" aria-label={t('Language of the question')}>
            {[['all', t('Both languages')], ['ar', t('Arabic')], ['en', t('English')]].map(([k, l]) =>
              <button key={k} aria-pressed={qlang === k} onClick={() => setQlang(k)}>{l}</button>)}
          </span>
          <span className="seg" role="group" aria-label={t('Window')}>
            {[4, 12].map((w) => <button key={w} aria-pressed={weeks === w} onClick={() => setWeeks(w)}>{t('{n} weeks', { n: w })}</button>)}
          </span>
        </div>
      </div>
      {err && <p className="err">{err}</p>}

      <div className="row small" role="status" style={{ margin: '10px 0 8px' }}>
        {Object.entries(status).map(([k, s]) => (
          <span key={k} className="pill">
            <span aria-hidden="true" style={{ color: s === 'ok' ? 'var(--good)' : s === 'error' ? 'var(--critical)' : s === 'over_budget' || s === 'partial' ? 'var(--warning)' : 'var(--muted)' }}>●</span>
            {ASSISTANT[k] || k}: {STATUS[s] ? t(STATUS[s]) : s}
          </span>))}
        {data.window && <span className="muted">{t('{from} to {to}', { from: fmtDate(data.window.from), to: fmtDate(data.window.to) })} · {tn(data.n_answers || 0, '{n} answer', '{n} answers')}</span>}
      </div>

      {!data.n_answers ? <div className="empty">{t('No answers in this window yet. The audit runs once a week, early on Monday (UTC).')}</div> : (
        <>
          <p className="small muted" style={{ margin: '0 0 8px' }}>{t('The two bars in each block use different units: monitored coverage counts articles we collected, cited counts links in the answers. Compare the shares, not the sizes.')}</p>
          <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 320px), 1fr))' }}>
            {providers.map((p) => {
              const cited = total(p.cited_scope)
              const cl = p.cited_lang || {}
              const ql = p.query_lang || {}
              const clTotal = total(cl), qlTotal = total(ql)
              return (
                <div key={p.key} style={{ border: '1px solid var(--line)', borderRadius: 8, padding: 12, minWidth: 0 }}>
                  <h3 style={{ marginTop: 0 }}>{p.label || ASSISTANT[p.key] || p.key}</h3>
                  <p className="small" style={{ margin: '0 0 6px' }}>{tn(p.answers || 0, '{n} answer', '{n} answers')}
                    {p.no_search > 0 && <> · {tn(p.no_search, '{n} answer without a search', '{n} answers without a search')}</>}</p>
                  <table className="data"><tbody>
                    <tr><th>{t('Sources searched per answer, median (range)')}</th><td className="num" style={{ whiteSpace: 'nowrap' }}>{spread(p.searched_per_answer)}</td></tr>
                    <tr><th>{t('Sources cited per answer, median (range)')}</th><td className="num" style={{ whiteSpace: 'nowrap' }}>{spread(p.cited_per_answer)}</td></tr>
                  </tbody></table>
                  <div className="small" style={{ marginTop: 10 }}><b>{t('Monitored coverage')}</b> <span className="muted">{t('share of articles, by outlet scope')}</span></div>
                  {covTotal ? <MixBar parts={parts(data.coverage_scope)} labels={labels} colors={SCOPE_COLOR} height={12} />
                    : <p className="small muted">{t('No monitored articles in this window.')}</p>}
                  <div className="small" style={{ marginTop: 10 }}><b>{t('Cited by the assistant')}</b> <span className="muted">{t('share of cited links, by outlet scope')}</span></div>
                  {cited ? <MixBar parts={parts(p.cited_scope)} labels={labels} colors={SCOPE_COLOR} height={12} />
                    : <p className="small muted">{t('No cited links in this window.')}</p>}
                  <p className="small" style={{ margin: '10px 0 2px' }}>{clTotal ? t('Cited sources by language: Arabic {ar}%, English {en}%, other {other}%', {
                    ar: pct(cl.ar || 0, clTotal), en: pct(cl.en || 0, clTotal), other: pct(cl.other || 0, clTotal) }) : t('Cited sources by language: none yet')}</p>
                  <p className="small muted" style={{ margin: 0 }}>{qlTotal ? t('Its own searches by language: Arabic {ar}%, English {en}%, other {other}%', {
                    ar: pct(ql.ar || 0, qlTotal), en: pct(ql.en || 0, qlTotal), other: pct(ql.other || 0, qlTotal) }) : t('Its own searches by language: none yet')}</p>
                </div>)
            })}
          </div>

          <h3>{t('Most cited outlets and domains')}</h3>
          {!one && <p className="small muted" style={{ marginTop: 0 }}>{t('One column per assistant. Choose one assistant to see how often each source also appeared in search results.')}</p>}
          {!(data.top_outlets || []).length ? <p className="small muted">{t('No cited links in this window.')}</p> : (
            <div className="scroll" style={{ maxHeight: 420 }}>
              <table className="data">
                <thead><tr><th>{t('Outlet or domain')}</th><th>{t('Scope')}</th>
                  {one ? <><th className="num">{t('Cited')}</th><th className="num" title={t('Times it appeared in search results')}>{t('Searched')}</th></>
                    : providers.map((p) => <th key={p.key} className="num">{t('Cited by {assistant}', { assistant: ASSISTANT[p.key] || p.label })}</th>)}
                </tr></thead>
                <tbody>{data.top_outlets.map((r) => {
                  const href = siteUrl(r.domain)
                  return (
                    <tr key={r.outlet_id ?? `d:${r.domain}`}>
                      <td>{r.outlet_id != null
                        ? <button className="linkish" dir="auto" onClick={() => openOutlet(r.outlet_id)}>{r.name}</button>
                        : <span dir="auto">{r.name}</span>}
                        <div className="small muted"><span dir="ltr">{r.domain}</span>
                          {href && <> <a href={href} target="_blank" rel="noreferrer noopener" aria-label={t('Open {domain}', { domain: r.domain })}>↗</a></>}
                          {r.outlet_id == null && <> <span className="pill">{t('not in the register')}</span></>}</div></td>
                      <td className="small">{labels[r.scope] || (r.outlet_id == null ? labels.unregistered : labels.unknown_scope)}</td>
                      {one ? <><td className="num">{fmtNum(r.cited)}</td><td className="num">{fmtNum(r.searched)}</td></>
                        : providers.map((p) => <td key={p.key} className="num">{fmtNum(r.by_provider?.[p.key] ?? 0)}</td>)}
                    </tr>)
                })}</tbody>
              </table>
            </div>)}

          <h3>{t('Libyan outlets never cited ({n})', { n: never.length })}</h3>
          <p className="small muted" style={{ marginTop: 0 }}>{t('Libyan outlets in the register with articles in the last 12 weeks that no answer in this window cited. With only {n} answers this is weak evidence about any single outlet.', { n: data.n_answers })}</p>
          {never.length === 0 ? <p className="small muted">{t('Every Libyan outlet with recent articles was cited at least once.')}</p> : (
            <>
              <div className="small" style={{ margin: '6px 0 4px' }}><b>{t('Appeared in search results, never cited ({n})', { n: never.filter((r) => r.appeared_in_results).length })}</b></div>
              {appeared.length ? <div className="chips">{appeared.map(chip)}</div> : <p className="small muted" style={{ margin: 0 }}>{t('None.')}</p>}
              <div className="small" style={{ margin: '10px 0 4px' }}><b>{t('Never appeared in search results ({n})', { n: never.filter((r) => !r.appeared_in_results).length })}</b></div>
              {unseen.length ? <div className="chips">{unseen.map(chip)}</div> : <p className="small muted" style={{ margin: 0 }}>{t('None.')}</p>}
              {never.length > NEVER_SHOWN && <button className="btn small ghost" style={{ marginTop: 6 }} onClick={() => setAllNever(!allNever)}>
                {allNever ? t('Show fewer') : t('Show all {n}', { n: never.length })}</button>}
            </>)}
        </>)}

      <p className="small muted" style={{ marginTop: 14, marginBottom: 0 }}>
        {t('These answers come from the assistants’ developer APIs with web search on, not from the apps people use, which can answer differently. It is one fixed set of questions, so it says nothing about other topics. Each assistant is counted on its own and the counts are never added together, because the two services define searched and cited differently. Nothing here is part of any gap score. The answers themselves are not kept, only which sources were searched and cited.')}
      </p>
    </section>
  )
}
