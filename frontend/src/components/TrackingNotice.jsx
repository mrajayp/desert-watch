import { api } from '../api'
import { useApp } from '../App'

export default function TrackingNotice() {
  const { setMe } = useApp()
  const answer = async (optOut) => {
    const me = await api('/api/me', { method: 'PATCH', body: { ack_tracking_notice: true, tracking_opt_out: optOut } })
    setMe(me)
  }
  return (
    <>
      <div className="drawer-backdrop" />
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="tn-title">
        <h2 id="tn-title" style={{ marginTop: 0 }}>How this tool learns from you</h2>
        <p>Desert Watch improves its rankings and topic matching from what the team does:</p>
        <ul>
          <li><b>Always recorded</b> (they are your contributions): votes on gaps, comments, articles you add, corrections and article assessments.</li>
          <li><b>Recorded unless you opt out</b>: which gaps and articles you view, click and spend time on, and the filters you use.</li>
        </ul>
        <p className="small">Behaviour is stored under a pseudonymous ID, never sent to third-party analytics, and raw logs are deleted after 12 months.
          Comments and “working on this” flags are visible to your team only. You can export or delete your data on the Privacy page at any time.</p>
        <div className="row" style={{ justifyContent: 'flex-end' }}>
          <button className="btn" onClick={() => answer(true)}>Opt out of behaviour tracking</button>
          <button className="btn primary" onClick={() => answer(false)}>OK, help it learn</button>
        </div>
      </div>
    </>
  )
}
