import { useEffect, useId, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useApp } from '../App'
import { DIMENSIONS, LENS_TEXT } from '../charts/scales'
import { weekRange } from '../charts/trendText'
import { groupLabel, themeLabel } from '../charts/util'
import { PHONE, useMedia } from '../hooks/useMedia'
import { getLang, pick, t } from '../i18n'
import { lensPatch } from '../lensWeek'

// The page's filters. The lens is a row of chips with its description as visible text (a labelled
// select on a phone); the week reads "Week of 5 to 11 Oct 2026" with previous and next buttons (the
// slider and play stay on wider screens); the theme and the outlet colouring are selects. A page
// leaves out the controls it does not use.
export default function Filters({ showLens = true, showTheme = true, showColor = true, showWeek = true, children }) {
  const { meta, filters, setFilters } = useApp()
  const phone = useMedia(PHONE)
  const [playing, setPlaying] = useState(false)
  const timer = useRef(null)
  const lensLabelId = useId()
  const weeks = meta.weeks
  const wi = Math.max(0, weeks.indexOf(filters.week))
  useEffect(() => {
    if (!playing) return
    timer.current = setInterval(() => {
      setFilters({ week: weeks[(weeks.indexOf(filters.week) + 1) % weeks.length] })
    }, 1100)
    return () => clearInterval(timer.current)
  }, [playing, filters.week, weeks, setFilters])
  useEffect(() => { if (playing && (phone || weeks.indexOf(filters.week) === weeks.length - 1)) setPlaying(false) }, [filters.week, playing, weeks, phone])

  const lensText = (l) => LENS_TEXT[l.key]
  const lensName = (l) => lensText(l)?.label || l.key
  // an unavailable lens says what it is waiting for, in the option and under the control
  const lensNote = (l) => (l.available ? lensText(l)?.blurb : `${lensName(l)}: ${lensText(l)?.waiting || t('waiting for data source key')}`)
  const current = meta.lenses.find((l) => l.key === filters.lens)
  const pickLens = (key) => setFilters(lensPatch(meta, filters, key))
  const goWeek = (i) => { setPlaying(false); setFilters({ week: weeks[Math.max(0, Math.min(weeks.length - 1, i))] }) }

  return (
    <div className="filters" role="group" aria-label={t('Filters')}>
      {showLens && (
        <div className="lens">
          <div className="row">
            <span id={lensLabelId} className="lens-label">{t('Compare coverage with:')}</span>
            {phone ? (
              <select value={filters.lens} onChange={(e) => pickLens(e.target.value)} aria-labelledby={lensLabelId}>
                {meta.lenses.map((l) => <option key={l.key} value={l.key} disabled={!l.available}>{l.available ? lensName(l) : lensNote(l)}</option>)}
              </select>
            ) : (
              <div className="chips" role="group" aria-labelledby={lensLabelId}>
                {meta.lenses.map((l) => (
                  <button key={l.key} type="button" className="chip" aria-pressed={filters.lens === l.key} disabled={!l.available}
                    onClick={() => pickLens(l.key)}>{lensName(l)}</button>))}
              </div>)}
          </div>
          {current && <p className="lens-blurb small muted">{lensNote(current)} · <Link to="/help#lens">{t('What is a lens?')}</Link></p>}
        </div>)}
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
        <div className="week" role="group" aria-label={t('Week')}>
          <button type="button" className="btn small week-arrow" disabled={wi <= 0} aria-label={t('Previous week')} onClick={() => goWeek(wi - 1)}>‹</button>
          <span className="week-label">{filters.week ? t('Week of {range}', { range: weekRange(filters.week) }) : ''}</span>
          <button type="button" className="btn small week-arrow" disabled={wi >= weeks.length - 1} aria-label={t('Next week')} onClick={() => goWeek(wi + 1)}>›</button>
          {!phone && (
            <>
              <input type="range" min={0} max={weeks.length - 1} value={wi} aria-label={t('Week')}
                onChange={(e) => goWeek(+e.target.value)} />
              <button type="button" className="btn small" onClick={() => {
                if (!playing && wi === weeks.length - 1) setFilters({ week: weeks[0] })
                setPlaying(!playing)
              }} aria-label={playing ? t('Pause') : t('Play weeks')}>{playing ? '❚❚' : '▶'}</button>
            </>)}
        </div>)}
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
