// Engagement for one article, on its meta line: how many outlets carried the story, and Facebook
// link engagement when we have a reading. Renders nothing when there is no data.
// Never used to rank outlets against each other: counts differ hugely by outlet.
import { N_, fmtDate, fmtNum, isAr, t } from '../i18n'

export const compact = (n) => {
  if (n < 1000) return String(Math.round(n))
  const [d, unit] = n < 999500 ? [1e3, 'k'] : [1e6, 'M']
  return `${(n / d).toFixed(n / d < 10 ? 1 : 0).replace(/\.0$/, '')}${unit}`
}

const AGE = { '48h': N_('about two days'), '7d': N_('about a week') }

export default function EngagementChip({ e }) {
  const pickup = e?.pickup >= 2 ? e.pickup : null
  const fb = e?.fb?.total != null ? e.fb : null
  if (!pickup && !fb) return null
  const day = fb?.measured_at?.slice(0, 10)
  const fbTitle = fb && (fb.total > 0
    ? t('Facebook engagement for this link: {n}, including {shares} shares and {comments} comments.', { n: fmtNum(Math.round(fb.total)), shares: fb.shares ?? 0, comments: fb.comments ?? 0 })
    : t('Facebook engagement for this link: {n}.', { n: fmtNum(Math.round(fb.total)) }))
    + ' ' + t('Facebook gives approximate counts.') + ' '
    + t('Read {age} after it was published, on {date}.', { age: AGE[fb.age_bucket] ? t(AGE[fb.age_bucket]) : fb.age_bucket, date: isAr() && day ? fmtDate(day) : day })
  return (
    <>
      {pickup && <span title={t('Outlets that ran the same story within two days. We match headlines, so rewritten or translated versions are missed. Only outlets we collect from count.')}>
        {' · '}{t('picked up by {n} outlets', { n: pickup })}</span>}
      {fb && <span title={fbTitle}>{' · '}{t('Facebook ≈ {n}', { n: compact(fb.total) })}</span>}
    </>
  )
}
