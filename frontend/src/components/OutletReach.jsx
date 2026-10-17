import { useEffect, useState } from 'react'
import { api } from '../api'
import { fmtNum, t } from '../i18n'
import { compact } from './EngagementChip'

// The outlet's reach, one dated line per source. Per outlet only: there is deliberately no table
// comparing outlets, because raw Facebook counts differ hugely between outlets.
export default function OutletReach({ id }) {
  const [r, setR] = useState(null)
  useEffect(() => { setR(null); api(`/api/outlets/${id}/reach`).then(setR).catch(() => setR({})) }, [id])
  if (!r) return null
  const tranco = r.tranco
  const h = r.facebook_historical
  const f = r.facebook_recent
  return (
    <>
      <h3>{t('Reach')}</h3>
      {!tranco && !h && !f ? <p className="muted small">{t('No reach figures for this outlet yet.')}</p> : (
        <ul className="list small">
          {f && <li>{t('Facebook engagement per article over the last {weeks} weeks: median {median}, from {n} articles read a week after publication.', { weeks: f.weeks ?? '', median: compact(f.median_7d), n: f.n ?? '' })}
            <div className="muted">{t('Approximate counts from Facebook.')}</div></li>}
          {tranco && <li>{tranco.value ? t('Web rank {rank} in the Tranco list, as of {date}.', { rank: fmtNum(tranco.value), date: tranco.as_of ?? '' })
            : t('Not in the Tranco list of the busiest websites, as of {date}.', { date: tranco.as_of ?? '' })}
            <div className="muted">{tranco.value ? t('A global ranking of websites by traffic. It says little about reach in Libya, where much of the news is read on Facebook.')
              : t('Web rank says little about reach in Libya, where much of the news is read on Facebook.')}</div></li>}
          {h && <li>{t('Facebook engagement per article {from} to {to}: {value} (historical).', { from: h.period?.from?.slice(0, 7) ?? '', to: h.period?.to?.slice(0, 7) ?? '', value: h.per_article != null ? fmtNum(h.per_article, { useGrouping: false }) : t('n/a') })}
            <div className="muted">{t('{engagements} engagements on {posts} Facebook posts linking {articles} of its articles. Source: {source}, {from} to {to}.', {
              engagements: fmtNum(h.fb_engagement ?? 0), posts: fmtNum(h.fb_posts ?? 0), articles: fmtNum(h.articles ?? 0),
              source: h.source || t('Social Media scraped data'), from: h.period?.from ?? '', to: h.period?.to ?? '' })}</div></li>}
        </ul>)}
    </>
  )
}
