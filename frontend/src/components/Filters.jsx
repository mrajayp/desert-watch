import { useEffect, useRef, useState } from 'react'
import { useApp } from '../App'
import { DIMENSIONS, LENS_TEXT } from '../charts/scales'
import { groupLabel, themeLabel } from '../charts/util'
import { getLang, pick, t } from '../i18n'
import { lensPatch } from '../lensWeek'

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
      <span className="seg" role="group" aria-label={t('Need lens')}>
        {meta.lenses.map((l) => (
          <button key={l.key} aria-pressed={filters.lens === l.key} disabled={!l.available}
            title={l.available ? LENS_TEXT[l.key]?.blurb : `${LENS_TEXT[l.key]?.label}: ${LENS_TEXT[l.key]?.waiting || t('waiting for data source key')}`}
            onClick={() => setFilters(lensPatch(meta, filters, l.key))}>{LENS_TEXT[l.key]?.label || l.key}</button>))}
      </span>
      {showTheme && (
        <label>{t('Theme')}
          <select value={filters.themeId} onChange={(e) => setFilters({ themeId: e.target.value })}>
            <option value="">{t('All themes')}</option>
            {[...new Set(meta.themes.map((th) => th.group).filter(Boolean))].map((g) => (
              <optgroup key={g} label={groupLabel(g)}>
                <option value={`group:${g}`}>{t('All {group} themes', { group: groupLabel(g).toLowerCase() })}</option>
                {meta.themes.filter((th) => th.group === g).map((th) => <option key={th.id} value={th.id}>{themeLabel(th, getLang())}</option>)}
              </optgroup>))}
            <optgroup label={t('General')}>
              {meta.themes.filter((th) => !th.group).map((th) => <option key={th.id} value={th.id}>{pick(th, 'name')}</option>)}
            </optgroup>
          </select>
        </label>)}
      {showWeek && weeks.length > 0 && (
        <label>{t('Week ending')}
          <button className="btn small" onClick={() => {
            if (!playing && wi === weeks.length - 1) setFilters({ week: weeks[0] })
            setPlaying(!playing)
          }} aria-label={playing ? t('Pause') : t('Play weeks')}>{playing ? '❚❚' : '▶'}</button>
          <input type="range" min={0} max={weeks.length - 1} value={wi} aria-label={t('Week')}
            onChange={(e) => { setPlaying(false); setFilters({ week: weeks[+e.target.value] }) }} />
          <span className="mono">{filters.week}</span>
        </label>)}
      {showColor && (
        <label>{t('Colour outlets by')}
          <select value={filters.colorBy} onChange={(e) => setFilters({ colorBy: e.target.value })}>
            {Object.entries(DIMENSIONS).map(([k, d]) => <option key={k} value={k}>{d.label}</option>)}
          </select>
        </label>)}
      {children}
    </div>
  )
}
