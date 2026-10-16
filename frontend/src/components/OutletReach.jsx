import { useEffect, useState } from 'react'
import { api } from '../api'
import { compact } from './EngagementChip'

// The outlet's reach, one dated line per source. Per outlet only: there is deliberately no table
// comparing outlets, because raw Facebook counts differ hugely between outlets.
export default function OutletReach({ id }) {
  const [r, setR] = useState(null)
  useEffect(() => { setR(null); api(`/api/outlets/${id}/reach`).then(setR).catch(() => setR({})) }, [id])
  if (!r) return null
  const t = r.tranco
  const h = r.facebook_historical
  const f = r.facebook_recent
  return (
    <>
      <h3>Reach</h3>
      {!t && !h && !f ? <p className="muted small">No reach figures for this outlet yet.</p> : (
        <ul className="list small">
          {f && <li>Facebook engagement per article over the last {f.weeks} weeks: median {compact(f.median_7d)}, from {f.n} articles read a week after publication.
            <div className="muted">Approximate counts from Facebook.</div></li>}
          {t && <li>{t.value ? `Web rank ${t.value.toLocaleString()} in the Tranco list, as of ${t.as_of}.`
            : `Not in the Tranco list of the busiest websites, as of ${t.as_of}.`}
            <div className="muted">{t.value ? 'A global ranking of websites by traffic. It says' : 'Web rank says'} little about reach in Libya, where much of the news is read on Facebook.</div></li>}
          {h && <li>Facebook engagement per article {h.period?.from?.slice(0, 7)} to {h.period?.to?.slice(0, 7)}: {h.per_article ?? 'n/a'} (historical).
            <div className="muted">{(h.fb_engagement ?? 0).toLocaleString()} engagements on {(h.fb_posts ?? 0).toLocaleString()} Facebook posts linking {(h.articles ?? 0).toLocaleString()} of its articles. Source: {h.source || 'Social Media scraped data'}, {h.period?.from} to {h.period?.to}.</div></li>}
        </ul>)}
    </>
  )
}
