// Timeline: key events overlaid on monthly coverage per theme, with official statements and
// humanitarian reports as separate streams (not counted as media coverage).
import * as d3 from 'd3'
import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api'
import { useApp } from '../App'
import { fmt } from '../charts/scales'
import { ExportMenu, fitLabel, themeLabel, useSize, useTooltip } from '../charts/util'
import WikiReading from '../components/WikiReading'

const RANGES = [['all', 'All'], ['24', '24 months'], ['12', '12 months']]

export default function Timeline() {
  const { meta, lang, me } = useApp()
  const [data, setData] = useState(null)
  const [range, setRange] = useState('all')
  const [group, setGroup] = useState('all')
  const [hoverEv, setHoverEv] = useState(null)
  const [form, setForm] = useState({ day: '', label: '', theme_id: '', source_url: '' })
  const [msg, setMsg] = useState(null)
  const svgRef = useRef(null)
  const wrap = useRef(null)
  const W = useSize(wrap, 1100)
  const tip = useTooltip()
  const load = () => api('/api/timeline').then(setData)
  useEffect(() => { load() }, [])

  const view = useMemo(() => {
    if (!data || !data.months.length) return null
    const n = range === 'all' ? data.months.length : Math.min(data.months.length, +range)
    const start = data.months.length - n
    const months = data.months.slice(start)
    const themes = meta.themes.filter((t) => group === 'all' || (group === 'general' ? !t.group : t.group === group))
    const rows = []
    rows.push({ kind: 'events' })
    rows.push({ kind: 'stream', key: 'statements', label: 'Official statements (UN, embassies, governments)', values: data.statements.slice(start) })
    rows.push({ kind: 'stream', key: 'reports', label: 'Humanitarian reports (ReliefWeb)', values: data.reports.slice(start) })
    const groups = [...new Set(themes.map((t) => t.group || ''))]
    for (const g of groups) {
      rows.push({ kind: 'header', label: g ? g[0].toUpperCase() + g.slice(1) : 'General themes' })
      for (const t of themes.filter((x) => (x.group || '') === g)) {
        rows.push({ kind: 'theme', theme: t, values: (data.themes[t.id] || []).slice(start) })
      }
    }
    const first = months[0], last = months[months.length - 1]
    const events = data.events.filter((e) => e.day.slice(0, 7) >= first && e.day.slice(0, 7) <= last
      && (group === 'all' || !e.theme_id || themes.some((t) => t.id === e.theme_id)))
    return { months, rows, events }
  }, [data, range, group, meta.themes])

  if (!data) return <main className="page"><div className="empty">Loading…</div></main>
  if (!view) return <main className="page"><div className="empty">No coverage collected yet.</div></main>

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
    const w = Math.min(220, ctx.measureText(e.label).width + 10)
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
  const themeName = (id) => meta.themes.find((t) => t.id === id)?.name_en
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
  const addEvent = async (e) => {
    e.preventDefault()
    try {
      await api('/api/key-events', { method: 'POST', body: { ...form, theme_id: form.theme_id ? +form.theme_id : null } })
      setForm({ day: '', label: '', theme_id: '', source_url: '' }); setMsg('Added.'); load()
    } catch (ex) { setMsg(ex.message) }
  }
  const removeEvent = async (id) => { await api(`/api/key-events/${id}`, { method: 'DELETE' }); load() }
  const caption = 'Source: Desert Watch monitored coverage (relevant articles per theme per month), official statements and ReliefWeb reports as separate streams.\n' +
    'Older months come from backfilled search, which returns fewer items: compare shapes, not levels, across years. Events: config + team, each with a source link.'

  return (
    <main className="page">
      <section className="card">
        <div className="card-head">
          <div><h2>Timeline: events, statements and coverage</h2>
            <p className="sub">Key events (top) over monthly coverage per theme. Each theme row is scaled to its own peak, so read shapes within a row. Hover an event to trace it through every row.</p></div>
          <div className="row">
            <span className="seg" role="group" aria-label="Range">{RANGES.map(([k, l]) => <button key={k} aria-pressed={range === k} onClick={() => setRange(k)}>{l}</button>)}</span>
            <span className="seg" role="group" aria-label="Themes">{[['all', 'All'], ['general', 'General'], ['gender', 'Gender']].map(([k, l]) =>
              <button key={k} aria-pressed={group === k} onClick={() => setGroup(k)}>{l}</button>)}</span>
            <ExportMenu svgRef={svgRef} title={`Timeline: events and coverage, ${meta.country.name_en}`} caption={caption} filename="timeline" />
          </div>
        </div>
        <div ref={wrap} className="viz" onMouseLeave={() => { tip.hide(); setHoverEv(null) }}>
          <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Timeline of key events and monthly coverage per theme">
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
                  <text x={left - 10} y={y0 + 14} textAnchor="end" style={{ fontSize: 12, fontWeight: 600, fill: 'var(--ink)' }}>Key events</text>
                  {placed.filter((e) => e.lane < laneCount).map((e) => (
                    <g key={e.id} transform={`translate(${e.x},${y0 + 6 + e.lane * 16})`} style={{ cursor: 'pointer' }}
                      onMouseEnter={(ev) => { setHoverEv(e.id); tip.show(ev, <div><b>{e.day}</b><div>{e.label}</div>
                        {e.theme_id && <div className="small muted">{themeName(e.theme_id)}</div>}
                        <div className="small muted">{e.origin === 'user' ? 'added by the team' : 'reference event'} · click for source</div></div>, wrap.current) }}
                      onClick={() => e.source_url && window.open(e.source_url, '_blank', 'noopener,noreferrer')}>
                      <circle r={4} cy={6} fill={hoverEv === e.id ? 'var(--ink)' : 'var(--surface)'} stroke="var(--ink)" strokeWidth={1.5} />
                      <text x={7} y={10} style={{ fontSize: 11, fill: 'var(--ink)', paintOrder: 'stroke', stroke: 'var(--surface)', strokeWidth: 3 }}>
                        {fitLabel(e.label, Math.min(e.w, W - right - e.x - 10), '11px system-ui, sans-serif')}</text>
                    </g>))}
                </g>)
              const label = r.kind === 'theme' ? themeLabel(r.theme, lang) : r.label
              const hl = r.kind === 'theme' && hoverEv != null && placed.find((e) => e.id === hoverEv)?.theme_id === r.theme.id
              return (
                <g key={r.key || r.theme.id}>
                  {hl && <rect x={0} y={y0} width={W} height={rowH[r.kind]} fill="var(--surface-2)" />}
                  <text x={left - 10} y={y0 + rowH[r.kind] / 2 + 4} textAnchor="end" style={{ fontSize: 12, fill: r.kind === 'stream' ? 'var(--ink-2)' : 'var(--ink)', fontStyle: r.kind === 'stream' ? 'italic' : 'normal' }}>
                    <title>{r.kind === 'theme' ? r.theme.name_en : r.label}</title>{fitLabel(label, left - 16)}</text>
                  <line x1={left} x2={W - right} y1={y0 + rowH[r.kind] - 4} y2={y0 + rowH[r.kind] - 4} stroke="var(--grid)" />
                  {bars(r.values, y0, rowH[r.kind], r.kind === 'stream' ? 'var(--ink-2)' : r.theme.group ? 'var(--al-3)' : 'var(--accent)', label)}
                  <text x={W - right} y={y0 + 10} textAnchor="end" className="num" style={{ fontSize: 9, fill: 'var(--muted)' }}>peak {fmt(d3.max(r.values) || 0)}</text>
                </g>)
            })}
          </svg>
          {tip.node}
        </div>
        <div className="legend" style={{ marginTop: 6 }}>
          <span><span className="sw" style={{ background: 'var(--accent)' }} />General themes (articles/month)</span>
          <span><span className="sw" style={{ background: 'var(--al-3)' }} />Gender themes</span>
          <span><span className="sw" style={{ background: 'var(--ink-2)' }} />Official statements / humanitarian reports (not counted as coverage)</span>
          {lanes.length > laneCount && <span className="muted">{lanes.length - laneCount} more event lanes hidden at this width; zoom the range to see them.</span>}
        </div>
      </section>
      <div className="grid halves" style={{ marginTop: 16 }}>
        <section className="card">
          <h2>Add a key event</h2>
          <p className="sub">Events appear on the timeline for the whole team. A source link is required.</p>
          <form className="form" onSubmit={addEvent}>
            <div className="row">
              <label>Date<input type="text" placeholder="YYYY-MM-DD" value={form.day} onChange={(e) => setForm({ ...form, day: e.target.value })} required pattern="\d{4}-\d{2}-\d{2}" /></label>
              <label style={{ flex: 1 }}>Theme (optional)
                <select value={form.theme_id} onChange={(e) => setForm({ ...form, theme_id: e.target.value })}>
                  <option value="">— none —</option>{meta.themes.map((t) => <option key={t.id} value={t.id}>{t.name_en}</option>)}</select></label>
            </div>
            <label>What happened<input type="text" dir="auto" maxLength={200} value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} required /></label>
            <label>Source link<input type="url" value={form.source_url} onChange={(e) => setForm({ ...form, source_url: e.target.value })} required /></label>
            <div className="row"><button className="btn primary">Add event</button>{msg && <span className="small">{msg}</span>}</div>
          </form>
        </section>
        <section className="card">
          <h2>Events ({data.events.length})</h2>
          <ul className="list small scroll" style={{ maxHeight: 360 }}>{[...data.events].reverse().map((e) => (
            <li key={e.id}><b>{e.day}</b> · <span dir="auto">{e.label}</span>{e.theme_id && <span className="muted"> · {themeName(e.theme_id)}</span>}
              {' '}<a href={e.source_url} target="_blank" rel="noreferrer noopener">source</a>
              {e.origin === 'user' && <span className="muted"> · added by the team</span>}
              {e.origin === 'user' && (me.role === 'admin' || e.mine) &&
                <button className="btn small ghost" onClick={() => removeEvent(e.id)}>remove</button>}</li>))}</ul>
        </section>
      </div>
      <section className="card" style={{ marginTop: 16 }}>
        <h2>What people in Libya read on Wikipedia</h2>
        <p className="sub">Libya pages that people in Libya read each day, from Wikimedia's privacy-protected figures. Most days only a few pages make it. The days with many are days when something happened.</p>
        <WikiReading />
      </section>
    </main>
  )
}
