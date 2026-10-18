// A warning on a gap (coverage dropped while need held, little Arabic coverage, only one side
// covers it...) as a pill with a glyph and a border as well as the colour, so it is never colour alone.
// The informational codes (most coverage names no place, need data stops early) keep the plain pill.
// The codes come from the API; charts/scales.js has their words.
import { INFO_FLAGS, flagText } from '../charts/scales'
import { t } from '../i18n'

export function WarningPill({ code, style }) {
  const info = INFO_FLAGS.has(code)
  return (
    <span className={info ? 'pill' : 'pill flag'} style={style}>
      {!info && <span className="glyph" aria-hidden="true">⚠︎</span>}
      {!info && <span className="sr-only">{t('Warning:')} </span>}
      {flagText(code)}
    </span>
  )
}

// every warning of a gap; block: one under the other (in a tooltip)
export function WarningPills({ codes, block = false }) {
  if (!codes?.length) return null
  return codes.map((f) => (block
    ? <div key={f} style={{ marginTop: 3 }}><WarningPill code={f} /></div>
    : <WarningPill key={f} code={f} />))
}
