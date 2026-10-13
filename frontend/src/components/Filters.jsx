import { useEffect, useRef, useState } from 'react'
import { useApp } from '../App'
import { DIMENSIONS, LENS_TEXT } from '../charts/scales'

export default function Filters({ showTheme = true, showColor = true, showWeek = true, children }) {
  const { meta, filters, setFilters } = useApp()
  const [playing, setPlaying] = useState(false)
  const timer = useRef(null)
  const weeks = meta.weeks
  const wi = Math.max(0, weeks.indexOf(filters.week))
  useEffect(() => {
    if (!playing) return
    timer.current = setInterval(() => {
      setFilters({ week: weeks[(weeks.indexOf(filters.week) + 1) % weeks.length] })
    }, 1100)
    return () => clearInterval(timer.current)
  }, [playing, filters.week, weeks, setFilters])
  useEffect(() => { if (playing && weeks.indexOf(filters.week) === weeks.length - 1) setPlaying(false) }, [filters.week, playing, weeks])

  return (
    <div className="filters" role="search">
      <span className="seg" role="group" aria-label="Need lens">
        {meta.lenses.map((l) => (
          <button key={l.key} aria-pressed={filters.lens === l.key} disabled={!l.available}
            title={l.available ? LENS_TEXT[l.key]?.blurb : `${LENS_TEXT[l.key]?.label}: waiting for data source key`}
            onClick={() => setFilters({ lens: l.key })}>{LENS_TEXT[l.key]?.label || l.key}</button>))}
      </span>
      {showTheme && (
        <label>Theme
          <select value={filters.themeId} onChange={(e) => setFilters({ themeId: e.target.value })}>
            <option value="">All themes</option>
            {[...new Set(meta.themes.map((t) => t.group).filter(Boolean))].map((g) => (
              <optgroup key={g} label={g[0].toUpperCase() + g.slice(1)}>
                <option value={`group:${g}`}>All {g} themes</option>
                {meta.themes.filter((t) => t.group === g).map((t) => <option key={t.id} value={t.id}>{t.name_en.replace(/^[^:]+:\s*/, '')}</option>)}
              </optgroup>))}
            <optgroup label="General">
              {meta.themes.filter((t) => !t.group).map((t) => <option key={t.id} value={t.id}>{t.name_en}</option>)}
            </optgroup>
          </select>
        </label>)}
      {showWeek && weeks.length > 0 && (
        <label>Week ending
          <button className="btn small" onClick={() => {
            if (!playing && wi === weeks.length - 1) setFilters({ week: weeks[0] })
            setPlaying(!playing)
          }} aria-label={playing ? 'Pause' : 'Play weeks'}>{playing ? '❚❚' : '▶'}</button>
          <input type="range" min={0} max={weeks.length - 1} value={wi} aria-label="Week"
            onChange={(e) => { setPlaying(false); setFilters({ week: weeks[+e.target.value] }) }} />
          <span className="mono">{filters.week}</span>
        </label>)}
      {showColor && (
        <label>Colour outlets by
          <select value={filters.colorBy} onChange={(e) => setFilters({ colorBy: e.target.value })}>
            {Object.entries(DIMENSIONS).map(([k, d]) => <option key={k} value={k}>{d.label}</option>)}
          </select>
        </label>)}
      {children}
    </div>
  )
}
