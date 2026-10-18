// Timeline: key events overlaid on monthly coverage per theme, with official statements and
// humanitarian reports as separate streams (not counted as media coverage).
import * as d3 from 'd3'
import { useMemo, useRef, useState } from 'react'
import { api } from '../api'
import { useApp } from '../App'
import { fmt } from '../charts/scales'
import { ExportMenu, fitLabel, themeLabel, useSize, useTooltip } from '../charts/util'
import { ErrorBox, Loading } from '../components/Notices'
import WikiReading from '../components/WikiReading'
import { useApi } from '../hooks/useApi'
import { useMutation } from '../hooks/useMutation'
import { usePageTitle } from '../hooks/usePageTitle'
import { N_, fmtDate, isAr, pick, t } from '../i18n'

const RANGES = [['all', N_('All')], ['24', N_('24 months')], ['12', N_('12 months')]]
const GROUPS = [['all', N_('All')], ['general', N_('General')], ['gender', N_('Gender')]]
// an event day (YYYY-MM-DD): as is in English, with Libyan month names in Arabic
const day = (d) => (isAr() ? fmtDate(d) : d)

export default function Timeline() {
  const { meta, lang, me, can } = useApp()
  usePageTitle(t('Timeline'))
  const q = useApi('/api/timeline')
  const data = q.data
  const [range, setRange] = useState('all')
  const [group, setGroup] = useState('all')
  const [hoverEv, setHoverEv] = useState(null)
  const [form, setForm] = useState({ day: '', label: '', theme_id: '', source_url: '' })
  const [msg, setMsg] = useState(null)
  const svgRef = useRef(null)
  const wrap = useRef(null)
  const W = useSize(wrap, 1100)
  const tip = useTooltip()
  const addEvent = useMutation((e) => { e.preventDefault(); return api('/api/key-events', { method: 'POST', body: { ...form, theme_id: form.theme_id ? +form.theme_id : null } }) },
    { onSuccess: () => { setForm({ day: '', label: '', theme_id: '', source_url: '' }); setMsg(t('Added.')); q.retry() } })
  const removeEvent = useMutation((id) => api(`/api/key-events/${id}`, { method: 'DELETE' }), { onSuccess: q.retry })

  const view = useMemo(() => {
    if (!data || !data.months.length) return null
    const n = range === 'all' ? data.months.length : Math.min(data.months.length, +range)
    const start = data.months.length - n
    const months = data.months.slice(start)
    const themes = meta.themes.filter((t) => group === 'all' || (group === 'general' ? !t.group : t.group === group))
    const rows = []
    rows.push({ kind: 'events' })
    rows.push({ kind: 'stream', key: 'statements', label: t('Official statements (UN, embassies, governments)'), values: data.statements.slice(start) })
    rows.push({ kind: 'stream', key: 'reports', label: t('Humanitarian reports (ReliefWeb)'), values: data.reports.slice(start) })
    const groups = [...new Set(themes.map((t) => t.group || ''))]
    for (const g of groups) {
      // a theme group key ('gender') shows as its capitalised name, translated when the catalogue has it
      rows.push({ kind: 'header', label: g ? t(g[0].toUpperCase() + g.slice(1)) : t('General themes') })
      for (const t of themes.filter((x) => (x.group || '') === g)) {
        rows.push({ kind: 'theme', theme: t, values: (data.themes[t.id] || []).slice(start) })
      }
    }
    const first = months[0], last = months[months.length - 1]
    const events = data.events.filter((e) => e.day.slice(0, 7) >= first && e.day.slice(0, 7) <= last
      && (group === 'all' || !e.theme_id || themes.some((t) => t.id === e.theme_id)))
    return { months, rows, events }
  }, [data, range, group, meta.themes])

  if (!data) return <main className="page">{q.error ? <ErrorBox error={q.error} onRetry={q.retry} /> : <Loading />}</main>
  if (!view) return <main className="page"><div className="empty">{t('No coverage collected yet.')}</div></main>

  const left = Math.min(260, Math.max(130, W * 0.24))
  const right = 12
  const x = d3.scaleBand().domain(view.months).range([left, W - right]).paddingInner(0.12)
  const dayX = (day) => {
    const m = day.slice(0, 7)
    const d = +day.slice(8, 10) || 15
    return x(m) == null ? null : x(m) + (x.bandwidth() * (d - 1)) / 30
  }
  // lay event labels into lanes so they don't overlap
  const ctx = document.createElement('canvas').getContext('2d'); ctx.font = '11px system-ui, sans-serif'
  const lanes = []
  const placed = view.events.map((e) => {
    const ex = dayX(e.day)
    const w = Math.min(220, ctx.measureText(pick(e, 'label')).width + 10)
    let lane = 0
    while ((lanes[lane] ?? -1e9) > ex - 4) lane++
    lanes[lane] = ex + w
    return { ...e, x: ex, lane, w }
  })
  const laneCount = Math.min(6, Math.max(1, lanes.length))
  const evH = 14 + laneCount * 16
  const rowH = { events: evH, stream: 30, header: 24, theme: 30 }
  let y = 26
  const ys = view.rows.map((r) => { const y0 = y; y += rowH[r.kind]; return y0 })
  const H = y + 6
  const themeName = (id) => pick(meta.themes.find((t) => t.id === id), 'name')
  const tickEvery = Math.max(1, Math.ceil(view.months.length / (W < 700 ? 6 : 14)))

  const bars = (values, y0, h, color, label) => {
    const max = d3.max(values) || 1
    return values.map((v, i) => {
      const m = view.months[i]
      const bh = v ? Math.max(2, ((h - 8) * v) / max) : 0
      return (
        <rect key={m} x={x(m)} y={y0 + h - 4 - bh} width={x.bandwidth()} height={bh} rx={1.5} fill={color}
          onMouseMove={(e) => tip.show(e, <div><b>{label}</b><div>{m}: {fmt(v)}</div></div>, wrap.current)} />)
    })
  }
  const caption = t('Source: Desert Watch monitored coverage (relevant articles per theme per month), official statements and ReliefWeb reports as separate streams.') + '\n' +
    t('Older months come from backfilled search, which returns fewer items: compare shapes, not levels, across years. Events: config + team, each with a source link.')

  return (
    <main className="page">
      <section className="card">
        <div className="card-head">
          <div><h2>{t('Timeline: events, statements and coverage')}</h2>
            <p className="sub">{t('Key events (top) over monthly coverage per theme. Each theme row is scaled to its own peak, so read shapes within a row. Hover an event to trace it through every row.')}</p></div>
          <div className="row">
            <span className="seg" role="group" aria-label={t('Range')}>{RANGES.map(([k, l]) => <button key={k} aria-pressed={range === k} onClick={() => setRange(k)}>{t(l)}</button>)}</span>
            <span className="seg" role="group" aria-label={t('Themes')}>{GROUPS.map(([k, l]) =>
              <button key={k} aria-pressed={group === k} onClick={() => setGroup(k)}>{t(l)}</button>)}</span>
            <ExportMenu svgRef={svgRef} title={t('Timeline: events and coverage, {country}', { country: pick(meta.country, 'name') })} caption={caption} filename="timeline" />
          </div>
        </div>
        <div ref={wrap} className="viz" onMouseLeave={() => { tip.hide(); setHoverEv(null) }}>
          <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={t('Timeline of key events and monthly coverage per theme')}>
            {view.months.map((m, i) => i % tickEvery === 0 && (
              <text key={m} x={x(m) + x.bandwidth() / 2} y={14} textAnchor="middle" style={{ fontSize: 10 }}>{m}</text>))}
            {/* event lines through all rows */}
            {placed.map((e) => (
              <line key={`l${e.id}`} x1={e.x} x2={e.x} y1={22} y2={H - 4} stroke="var(--ink)"
                strokeOpacity={hoverEv === e.id ? 0.7 : 0.12} strokeWidth={hoverEv === e.id ? 1.5 : 1} pointerEvents="none" />))}
            {view.rows.map((r, i) => {
              const y0 = ys[i]
              if (r.kind === 'header') return (
                <g key={`h${i}`}><text x={4} y={y0 + 16} style={{ fontSize: 11, fontWeight: 700, fill: 'var(--ink-2)', letterSpacing: '.04em' }}>{r.label.toUpperCase()}</text>
                  <line x1={4} x2={W - right} y1={y0 + 21} y2={y0 + 21} stroke="var(--grid)" /></g>)
              if (r.kind === 'events') return (
                <g key="ev">
                  <text x={left - 10} y={y0 + 14} textAnchor="end" style={{ fontSize: 12, fontWeight: 600, fill: 'var(--ink)' }}>{t('Key events')}</text>
                  {placed.filter((e) => e.lane < laneCount).map((e) => (
                    <g key={e.id} transform={`translate(${e.x},${y0 + 6 + e.lane * 16})`} style={{ cursor: 'pointer' }}
                      onMouseEnter={(ev) => { setHoverEv(e.id); tip.show(ev, <div><b>{day(e.day)}</b><div dir="auto">{pick(e, 'label')}</div>
                        {e.theme_id && <div className="small muted">{themeName(e.theme_id)}</div>}
                        <div className="small muted">{e.origin === 'user' ? t('added by the team') : t('reference event')} · {t('click for source')}</div></div>, wrap.current) }}
                      onClick={() => e.source_url && window.open(e.source_url, '_blank', 'noopener,noreferrer')}>
                      <circle r={4} cy={6} fill={hoverEv === e.id ? 'var(--ink)' : 'var(--surface)'} stroke="var(--ink)" strokeWidth={1.5} />
                      <text x={7} y={10} style={{ fontSize: 11, fill: 'var(--ink)', paintOrder: 'stroke', stroke: 'var(--surface)', strokeWidth: 3 }}>
                        {fitLabel(pick(e, 'label'), Math.min(e.w, W - right - e.x - 10), '11px system-ui, sans-serif')}</text>
                    </g>))}
                </g>)
              const label = r.kind === 'theme' ? themeLabel(r.theme, lang) : r.label
              const hl = r.kind === 'theme' && hoverEv != null && placed.find((e) => e.id === hoverEv)?.theme_id === r.theme.id
              return (
                <g key={r.key || r.theme.id}>
                  {hl && <rect x={0} y={y0} width={W} height={rowH[r.kind]} fill="var(--surface-2)" />}
                  <text x={left - 10} y={y0 + rowH[r.kind] / 2 + 4} textAnchor="end" style={{ fontSize: 12, fill: r.kind === 'stream' ? 'var(--ink-2)' : 'var(--ink)', fontStyle: r.kind === 'stream' ? 'italic' : 'normal' }}>
                    <title>{r.kind === 'theme' ? pick(r.theme, 'name') : r.label}</title>{fitLabel(label, left - 16)}</text>
                  <line x1={left} x2={W - right} y1={y0 + rowH[r.kind] - 4} y2={y0 + rowH[r.kind] - 4} stroke="var(--grid)" />
                  {bars(r.values, y0, rowH[r.kind], r.kind === 'stream' ? 'var(--ink-2)' : r.theme.group ? 'var(--al-3)' : 'var(--accent)', label)}
                  <text x={W - right} y={y0 + 10} textAnchor="end" className="num" style={{ fontSize: 9, fill: 'var(--muted)' }}>{t('peak {n}', { n: fmt(d3.max(r.values) || 0) })}</text>
                </g>)
            })}
          </svg>
          {tip.node}
        </div>
        <div className="legend" style={{ marginTop: 6 }}>
          <span><span className="sw" style={{ background: 'var(--accent)' }} />{t('General themes (articles/month)')}</span>
          <span><span className="sw" style={{ background: 'var(--al-3)' }} />{t('Gender themes')}</span>
          <span><span className="sw" style={{ background: 'var(--ink-2)' }} />{t('Official statements / humanitarian reports (not counted as coverage)')}</span>
          {lanes.length > laneCount && <span className="muted">{t('{n} more event lanes hidden at this width; zoom the range to see them.', { n: lanes.length - laneCount })}</span>}
        </div>
      </section>
      <div className="grid halves" style={{ marginTop: 16 }}>
        {can && (
          <section className="card">
            <h2>{t('Add a key event')}</h2>
            <p className="sub">{t('Events appear on the timeline for the whole team. A source link is required.')}</p>
            <form className="form" onSubmit={(e) => addEvent.run(e)}>
              <div className="row">
                <label>{t('Date')}<input type="text" placeholder={t('YYYY-MM-DD')} value={form.day} onChange={(e) => setForm({ ...form, day: e.target.value })} required pattern="\d{4}-\d{2}-\d{2}" /></label>
                <label style={{ flex: 1 }}>{t('Theme (optional)')}
                  <select value={form.theme_id} onChange={(e) => setForm({ ...form, theme_id: e.target.value })}>
                    <option value="">{t('— none —')}</option>{meta.themes.map((t) => <option key={t.id} value={t.id}>{pick(t, 'name')}</option>)}</select></label>
              </div>
              <label>{t('What happened')}<input type="text" dir="auto" maxLength={200} value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} required /></label>
              <label>{t('Source link')}<input type="url" value={form.source_url} onChange={(e) => setForm({ ...form, source_url: e.target.value })} required /></label>
              <div className="row"><button className="btn primary" disabled={addEvent.busy}>{t('Add event')}</button>{msg && <span className="small">{msg}</span>}</div>
              {addEvent.error && <ErrorBox error={addEvent.error} compact />}
            </form>
          </section>)}
        <section className="card">
          <h2>{t('Events ({n})', { n: data.events.length })}</h2>
          {removeEvent.error && <ErrorBox error={removeEvent.error} compact />}
          <ul className="list small scroll" style={{ maxHeight: 360 }}>{[...data.events].reverse().map((e) => (
            <li key={e.id}><b>{day(e.day)}</b> · <span dir="auto">{pick(e, 'label')}</span>{e.theme_id && <span className="muted"> · {themeName(e.theme_id)}</span>}
              {' '}<a href={e.source_url} target="_blank" rel="noreferrer noopener">{t('source')}</a>
              {e.origin === 'user' && <span className="muted"> · {t('added by the team')}</span>}
              {can && e.origin === 'user' && (me.role === 'admin' || e.mine) &&
                <button className="btn small ghost" disabled={removeEvent.busy} onClick={() => removeEvent.run(e.id)}>{t('remove')}</button>}</li>))}</ul>
        </section>
      </div>
      <section className="card" style={{ marginTop: 16 }}>
        <h2>{t('What people in Libya read on Wikipedia')}</h2>
        <p className="sub">{t('Libya pages that people in Libya read each day, from Wikimedia\'s privacy-protected figures. Most days only a few pages make it. The days with many are days when something happened.')}</p>
        <WikiReading />
      </section>
    </main>
  )
}
