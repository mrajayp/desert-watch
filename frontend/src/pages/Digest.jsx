import { Fragment, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { useApp } from '../App'
import { ErrorBox, Loading } from '../components/Notices'
import { useApi } from '../hooks/useApi'
import { useMutation } from '../hooks/useMutation'
import { usePageTitle } from '../hooks/usePageTitle'
import { LENS_TEXT } from '../charts/scales'
import { themeLabel } from '../charts/util'
import { weekRange } from '../charts/trendText'
import { N_, fmtDateTime, getLang, pick, t } from '../i18n'
import { articlesPath, gapPath } from '../routes'

// digest status codes from the API (shown for anything but 'ok')
const STATUS = { error: N_('error'), refused: N_('refused') }
const status = (s) => t(STATUS[s] || s)

// Minimal, safe Markdown: headings (with an optional {#id} anchor, the same in both languages), bullets,
// paragraphs, **bold**, *italic* and [text](url) links. A link may go to an http(s) page (opened in a
// new tab), to an #anchor on the page, or to a path inside this site (/me); anything else is shown as
// plain text. Text only, no HTML.
const SAFE_HREF = /^(https?:\/\/|#|\/(?![/\\]))/
const HEADING = /^(#{1,4})\s+(.*?)(?:\s*\{#([\w-]+)\})?\s*$/
const slug = (s) => s.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, '-').replace(/^-+|-+$/g, '')

function Href({ href, children }) {
  if (href.startsWith('#')) return <a href={href}>{children}</a>
  if (href.startsWith('/')) return <Link to={href}>{children}</Link>
  return <a href={href} target="_blank" rel="noreferrer noopener">{children}</a>
}

function inline(text) {
  const parts = []
  const re = /(\*\*[^*]+\*\*|\*[^*]+\*|\[([^\]]+)\]\(([^)\s]+)\))/g
  let last = 0, m
  while ((m = re.exec(text))) {
    if (m.index > last) parts.push(text.slice(last, m.index))
    const tok = m[0]
    if (tok.startsWith('[')) parts.push(SAFE_HREF.test(m[3]) ? <Href key={m.index} href={m[3]}>{inline(m[2])}</Href> : m[2])
    else parts.push(tok.startsWith('**') ? <strong key={m.index}>{inline(tok.slice(2, -2))}</strong> : <em key={m.index}>{inline(tok.slice(1, -1))}</em>)
    last = m.index + tok.length
  }
  if (last < text.length) parts.push(text.slice(last))
  return parts
}

export function Markdown({ text }) {
  const blocks = []
  let list = null
  for (const raw of (text || '').split('\n')) {
    const line = raw.trimEnd()
    const bullet = line.match(/^\s*[-*]\s+(.*)/)
    if (bullet) { (list ||= []).push(bullet[1]); continue }
    if (list) { blocks.push({ ul: list }); list = null }
    if (!line.trim()) continue
    const h = line.match(HEADING)
    blocks.push(h ? { h: h[1].length, text: h[2], id: h[3] || slug(h[2]) } : { p: line })
  }
  if (list) blocks.push({ ul: list })
  return (
    <div className="md" dir="auto">
      {blocks.map((b, i) => (
        <Fragment key={i}>
          {b.h && (b.h <= 2 ? <h3 id={b.id} style={{ marginTop: 18 }}>{inline(b.text)}</h3> : <h4 id={b.id}>{inline(b.text)}</h4>)}
          {b.p && <p>{inline(b.p)}</p>}
          {b.ul && <ul>{b.ul.map((li, j) => <li key={j}>{inline(li)}</li>)}</ul>}
        </Fragment>))}
    </div>
  )
}

// ---- the gaps a brief names ----------------------------------------------------------------------
// The facts a brief was written from carry its gaps (top_gaps: theme, region, lens, verdict, articles,
// and theme_id / region_id). Each one becomes a link to the gap view at the brief's week and lens, and
// to the articles the count covers (the facts' window). Without ids the names are matched to /api/meta.
const WINDOW = /^(\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})$/ // i18n-ok: the facts' window, two ISO days, never shown
export function gapLinks(facts, meta) {
  if (!facts?.top_gaps || !meta) return []
  const span = WINDOW.exec(facts.window || '')
  const out = []
  for (const g of facts.top_gaps) {
    const theme = meta.themes.find((x) => x.id === g.theme_id) || meta.themes.find((x) => x.name_en === g.theme)
    const region = meta.regions.find((x) => x.id === g.region_id) || meta.regions.find((x) => x.name_en === g.region)
    if (!theme || !region) continue
    out.push({
      theme, region, lens: g.lens, verdict: g.verdict, articles: g.articles,
      gap: gapPath(theme.id, region.id, { lens: g.lens, week: facts.week_starting }),
      articles_path: span ? articlesPath({ theme_id: theme.id, region_id: region.id, start: span[1], end: span[2] }) : null,
    })
  }
  return out
}
// the first mention of each linked theme in the brief becomes a Markdown link to its gap (one per theme,
// outside headings, never inside an existing link); the renderer turns it into a Link
export function linkify(md, links, lang) {
  let text = md || ''
  const done = new Set()
  for (const l of links) {
    if (done.has(l.theme.id)) continue
    const names = [...new Set([lang === 'ar' ? l.theme.name_ar : l.theme.name_en, themeLabel(l.theme, lang)].filter(Boolean))]
    const lines = text.split('\n')
    let hit = false
    for (let i = 0; i < lines.length && !hit; i++) {
      if (/^#/.test(lines[i])) continue
      for (const name of names) {
        const re = new RegExp(`(^|[^\\p{L}\\[])(${name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})(?![^\\[]*\\]\\()(?=$|[^\\p{L}])`, lang === 'ar' ? 'u' : 'iu')
        const m = re.exec(lines[i])
        if (!m) continue
        lines[i] = lines[i].slice(0, m.index + m[1].length) + `[${m[2]}](${l.gap})` + lines[i].slice(m.index + m[0].length)
        hit = true
        break
      }
    }
    if (hit) { text = lines.join('\n'); done.add(l.theme.id) }
  }
  return text
}

export default function DigestPage() {
  const { me, meta, lang } = useApp()
  usePageTitle(t('Digest'))
  const [picked, setPicked] = useState(null) // an archive entry the reader chose; else the latest good one
  const [showFacts, setShowFacts] = useState(false)
  const [msg, setMsg] = useState(null)
  const listQ = useApi('/api/digests')
  const list = listQ.data
  const first = list && (list.find((d) => d.status === 'ok') || list[0])
  const curId = picked ?? first?.id ?? null
  const curQ = useApi(curId ? `/api/digests/${curId}` : null)
  const cur = curQ.data
  const open = (id) => { setPicked(id); setShowFacts(false) }
  const links = useMemo(() => gapLinks(cur?.facts, meta), [cur, meta])
  const body = useMemo(() => (cur?.status === 'ok' ? linkify(cur.content_md, links, cur.lang || lang) : ''), [cur, links, lang])
  const regenerate = useMutation(() => api('/api/admin/run/digest', { method: 'POST' }),
    { onSuccess: () => setMsg(t('Generating… refresh in a minute. (Needs the ANTHROPIC_API_KEY secret on the server.)')) })
  return (
    <main className="page">
      <div className="grid two">
        <section className="card">
          {!list && listQ.error && <ErrorBox error={listQ.error} onRetry={listQ.retry} />}
          {!list && !listQ.error && <Loading />}
          {list && !first && (
            <div className="empty">
              {t('No digest yet. It is written about the week before, on Monday at 06:00 UTC. If Sunday’s Wikipedia views are not in by then, it tries again each morning up to Thursday. It needs an Anthropic API key on the server.')}
              {me.role === 'admin' && <><br /><br /><button className="btn" disabled={regenerate.busy} onClick={() => regenerate.run()}>{t('Generate now')}</button></>}
              {regenerate.error && <ErrorBox error={regenerate.error} compact />}
              {msg && <p className="small">{msg}</p>}
            </div>)}
          {list && first && !cur && curQ.error && <ErrorBox error={curQ.error} onRetry={curQ.retry} />}
          {list && first && !cur && !curQ.error && <Loading />}
          {cur && (
            <>
              <div className="card-head">
                <div><h2>{t('Weekly brief · week of {week}', { week: weekRange(cur.week_start) })}</h2>
                  <p className="sub">{t('Written by {model} from the facts below · {time} UTC', { model: cur.model, time: fmtDateTime(cur.created_at) })}
                    {cur.usage?.input_tokens ? <> · {t('{n} tokens', { n: cur.usage.input_tokens + cur.usage.output_tokens })}</> : ''}</p></div>
                {me.role === 'admin' && <button className="btn small" disabled={regenerate.busy} onClick={() => regenerate.run()}>{t('Regenerate')}</button>}
              </div>
              {regenerate.error && <ErrorBox error={regenerate.error} compact />}
              {curQ.error && <ErrorBox error={curQ.error} onRetry={curQ.retry} compact />}
              {msg && <p className="small">{msg}</p>}
              {cur.status === 'ok' && cur.lang && cur.lang !== getLang() &&
                <p className="small muted">{t('This brief was written before briefs were produced in Arabic too, so it is shown in English.')}</p>}
              {cur.status === 'ok' ? <Markdown text={body} /> : <div className="banner">{status(cur.status)}: {cur.error}</div>}
              {links.length > 0 && (
                <>
                  <h3>{t('Gaps named in this brief')}</h3>
                  <ul className="list small">{links.map((l) => (
                    <li key={`${l.theme.id}:${l.region.id}:${l.lens}`}>
                      <Link to={l.gap}>{pick(l.theme)} · {pick(l.region)}</Link>
                      <span className="muted"> · {t(LENS_TEXT[l.lens]?.label || l.lens)}</span>
                      {l.articles_path && l.articles != null && <> · <Link to={l.articles_path}>{t('{n} articles', { n: l.articles })}</Link></>}
                    </li>))}</ul>
                </>)}
              <p className="small muted" style={{ marginTop: 16 }}>{t('AI-written from the tool’s own counts; every number should appear in the facts. Check before quoting.')}</p>
              {me.role === 'admin' && <button className="btn small ghost" onClick={() => setShowFacts(!showFacts)}>{showFacts ? t('Hide the facts it was given') : t('Show the facts it was given')}</button>}
              {me.role === 'admin' && showFacts && <pre className="mono" style={{ whiteSpace: 'pre-wrap', maxHeight: 420, overflow: 'auto', background: 'var(--surface-2)', padding: 10, borderRadius: 6 }}>{JSON.stringify(cur.facts, null, 2)}</pre>}
            </>)}
        </section>
        <section className="card">
          <h2>{t('Archive')}</h2>
          <ul className="list">{(list || []).map((d) => (
            <li key={d.id}><button className="btn ghost" aria-pressed={cur?.id === d.id} onClick={() => open(d.id)}>{t('Week of {week}', { week: weekRange(d.week_start) })}</button>
              <span className="small muted"> {d.status !== 'ok' && status(d.status)}</span></li>))}</ul>
          {list && !list.length && <p className="muted small">{t('No briefs yet.')}</p>}
        </section>
      </div>
    </main>
  )
}
