// Engagement for one article, on its meta line: how many outlets carried the story, and Facebook
// link engagement when we have a reading. Renders nothing when there is no data.
// Never used to rank outlets against each other: counts differ hugely by outlet.

export const compact = (n) => {
  if (n < 1000) return String(Math.round(n))
  const [d, unit] = n < 1e6 ? [1e3, 'k'] : [1e6, 'M']
  return `${(n / d).toFixed(n / d < 10 ? 1 : 0).replace(/\.0$/, '')}${unit}`
}

const AGE = { '48h': 'about two days', '7d': 'about a week' }

export default function EngagementChip({ e }) {
  const pickup = e?.pickup >= 2 ? e.pickup : null
  const fb = e?.fb?.total != null ? e.fb : null
  if (!pickup && !fb) return null
  const fbTitle = fb && `Reactions, comments and shares on Facebook for this link: ${fb.reactions ?? 0} reactions, `
    + `${fb.comments ?? 0} comments, ${fb.shares ?? 0} shares. Facebook gives approximate counts. `
    + `Read ${AGE[fb.age_bucket] || fb.age_bucket} after it was published, on ${fb.measured_at?.slice(0, 10)}.`
  return (
    <>
      {pickup && <span title="Outlets that ran the same story within two days. We match headlines, so rewritten or translated versions are missed. Only outlets we collect from count.">
        {' · '}picked up by {pickup} outlets</span>}
      {fb && <span title={fbTitle}>{' · '}Facebook ≈ {compact(fb.total)}</span>}
    </>
  )
}
