// Engagement for one article, on its meta line: how many outlets carried the story, and Facebook
// link engagement when we have a reading. Renders nothing when there is no data.
// Never used to rank outlets against each other: counts differ hugely by outlet.
import { N_, fmtDate, fmtNum, t } from '../i18n'

// 1.2k, 3.4M in English; 1.2 ألف, 3.4 مليون in Arabic (Western digits either way)
export const compact = (n) => (n == null ? '' : fmtNum(n, { notation: 'compact', maximumFractionDigits: n < 1e4 ? 1 : 0 }))

const AGE = { '48h': N_('about two days'), '7d': N_('about a week') }

export default function EngagementChip({ e }) {
  const pickup = e?.pickup >= 2 ? e.pickup : null
  const fb = e?.fb?.total != null ? e.fb : null
  if (!pickup && !fb) return null
  const fbTitle = fb && (fb.total > 0
    ? t('Facebook engagement for this link: {n}, including {shares} shares and {comments} comments.', { n: fmtNum(Math.round(fb.total)), shares: fb.shares ?? 0, comments: fb.comments ?? 0 })
    : t('Facebook engagement for this link: {n}.', { n: fmtNum(Math.round(fb.total)) }))
    + ' ' + t('Facebook gives approximate counts.') + ' '
    + t('Read {age} after it was published, on {date}.', { age: AGE[fb.age_bucket] ? t(AGE[fb.age_bucket]) : fb.age_bucket, date: fmtDate(fb.measured_at) })
  return (
    <>
      {pickup && <span title={t('Outlets that ran the same story within two days. We match headlines, so rewritten or translated versions are missed. Only outlets we collect from count.')}>
        {' · '}{t('picked up by {n} outlets', { n: pickup })}</span>}
      {fb && <span title={fbTitle}>{' · '}{t('Facebook ≈ {n}', { n: compact(fb.total) })}</span>}
    </>
  )
}
