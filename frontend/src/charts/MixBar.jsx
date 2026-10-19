// A stacked share bar with its legend (the source mix of a gap, the scope mix of the outlets). Its own
// module, with no d3 in it, because the gap dialog is in the main chunk and must not drag the Trends
// charts (charts/Balance.jsx and the d3 scales they use) in with it.
import { t } from '../i18n.js'

export function MixBar({ parts, colors, labels, height = 12 }) {
  const total = Object.values(parts).reduce((a, b) => a + (b || 0), 0) || 1
  let acc = 0
  const entries = Object.entries(parts).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1])
  return (
    <div>
      <svg viewBox={`0 0 100 ${height}`} preserveAspectRatio="none" style={{ width: '100%', height }}>
        {entries.map(([k, v]) => {
          const w = (v / total) * 100
          const el = <rect key={k} x={acc} y={0} width={Math.max(0, w - 0.4)} height={height} fill={colors[k] || 'var(--cat-unknown)'} />
          acc += w
          return el
        })}
      </svg>
      <div className="legend" style={{ marginTop: 4 }}>
        {entries.map(([k, v]) => <span key={k}><span className="sw" style={{ background: colors[k] || 'var(--cat-unknown)' }} />{t(labels[k] || k)} {Math.round((v / total) * 100)}%</span>)}
      </div>
    </div>
  )
}
