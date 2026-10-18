// The lens picker of the This week page: a sheet from the foot of the screen listing the five lenses
// with their one-line descriptions and whether they have data yet, and a link to what a lens is.
// Picking one sets the page's lens (and moves a default week to the new lens's, as the filter bar does).
import { Link } from 'react-router-dom'
import { useApp } from '../App'
import { LENS_TEXT } from '../charts/scales'
import { t } from '../i18n'
import { lensPatch } from '../lensWeek'
import Dialog from './Dialog'

export default function LensSheet({ onClose }) {
  const { meta, filters, setFilters } = useApp()
  const choose = (key) => { setFilters(lensPatch(meta, filters, key)); onClose() }
  return (
    <Dialog mode="modal" variant="sheet" title={t('Choose a lens')} onClose={onClose} className="lens-sheet">
      <ul className="list lens-list">
        {meta.lenses.map((l) => {
          const x = LENS_TEXT[l.key]
          return (
            <li key={l.key}>
              <button type="button" className="lens-option" aria-pressed={filters.lens === l.key} disabled={!l.available} onClick={() => choose(l.key)}>
                <span className="t">{x?.label || l.key}</span>
                <span className="small muted">{l.available ? x?.blurb : t('Not available yet: {why}', { why: x?.waiting || t('waiting for data source key') })}</span>
              </button>
            </li>)
        })}
      </ul>
      <p className="small" style={{ margin: '10px 0 0' }}><Link to="/help#lens" onClick={onClose}>{t('What is a lens?')}</Link></p>
    </Dialog>
  )
}
