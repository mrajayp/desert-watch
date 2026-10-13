import { api } from '../api'
import { useApp } from '../App'

// Shown once on first login. There is no opt-out (owner decision 2026-10-13); the notice keeps
// what is recorded transparent.
export default function TrackingNotice() {
  const { setMe } = useApp()
  const ack = async () => setMe(await api('/api/me', { method: 'PATCH', body: { ack_tracking_notice: true } }))
  return (
    <>
      <div className="drawer-backdrop" />
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="tn-title">
        <h2 id="tn-title" style={{ marginTop: 0 }}>How this tool learns from the team</h2>
        <p>Desert Watch improves its rankings and topic matching from what the team does. It records your votes,
          comments, corrections, assessments and added articles, and also which gaps and articles you view, click
          and spend time on, and the filters you use.</p>
        <p className="small">Activity is stored under a pseudonymous ID, never sent to third-party analytics, and raw
          activity logs are deleted after 12 months. Comments and “working on this” flags are visible to your team only.
          You can export or delete your data on the Privacy page.</p>
        <div className="row" style={{ justifyContent: 'flex-end' }}>
          <button className="btn primary" onClick={ack}>OK</button>
        </div>
      </div>
    </>
  )
}
