import { api } from '../api'
import { useApp } from '../App'
import { useMutation } from '../hooks/useMutation'
import { t } from '../i18n'
import Dialog from './Dialog'
import { ErrorBox } from './Notices'

// Shown once on first login, before any view or click is recorded (the server drops events until it
// is acknowledged). There is no opt-out (owner decision 2026-10-13); the notice keeps what is recorded
// transparent. It cannot be dismissed any other way, so the dialog has no close.
export default function TrackingNotice() {
  const { setMe } = useApp()
  const ack = useMutation(() => api('/api/me', { method: 'PATCH', body: { ack_tracking_notice: true } }), { onSuccess: setMe })
  return (
    <Dialog mode="modal" variant="modal" title={t('How this tool learns from the team')}>
      <p>{t('Desert Watch improves its rankings and topic matching from what the team does. It records your votes, comments, corrections, assessments and added articles, and also which gaps and articles you view, click and spend time on, and the filters you use.')}</p>
      <p className="small">{t('Activity is stored under a pseudonymous ID, never sent to third-party analytics, and raw activity logs are deleted after 12 months. Comments and “working on this” flags are visible to your team only. You can export or delete your data on the Privacy page.')}</p>
      {ack.error && <ErrorBox error={ack.error} compact />}
      <div className="row" style={{ justifyContent: 'flex-end' }}>
        <button className="btn primary" disabled={ack.busy} onClick={() => ack.run()}>{t('OK')}</button>
      </div>
    </Dialog>
  )
}
