// What the app says about itself: the notice region (aria-live, errors stay until dismissed, notes
// fade), the offline banner, the inline error with Retry that replaces "Loading…" forever, and the
// one read-only notice a viewer sees per page.
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { ApiError } from '../api'
import { t } from '../i18n'

const Ctx = createContext({ notify: () => {}, dismiss: () => {} })
export const useNotices = () => useContext(Ctx)

let seq = 0

export function NoticesProvider({ children }) {
  const [items, setItems] = useState([])
  const dismiss = useCallback((id) => setItems((xs) => xs.filter((x) => x.id !== id)), [])
  // notify(text, { kind: 'error' | 'info' }); an error persists until dismissed, a note goes after 6 s
  const notify = useCallback((text, { kind = 'info' } = {}) => {
    const id = ++seq
    setItems((xs) => [...xs.filter((x) => x.text !== text), { id, text, kind }])
    if (kind !== 'error') setTimeout(() => dismiss(id), 6000)
    return id
  }, [dismiss])
  const value = useMemo(() => ({ notify, dismiss }), [notify, dismiss])
  return (
    <Ctx.Provider value={value}>
      {children}
      <Notices items={items} dismiss={dismiss} />
    </Ctx.Provider>
  )
}

function useOnline() {
  const [on, setOn] = useState(() => (typeof navigator === 'undefined' ? true : navigator.onLine !== false))
  useEffect(() => {
    const up = () => setOn(true), down = () => setOn(false)
    window.addEventListener('online', up); window.addEventListener('offline', down)
    return () => { window.removeEventListener('online', up); window.removeEventListener('offline', down) }
  }, [])
  return on
}

function Notices({ items, dismiss }) {
  const online = useOnline()
  return (
    <div className="notices" aria-live="polite">
      {!online && <div className="notice offline" role="status">{t('No connection. What you see was loaded earlier; changes will not be saved until you are back online.')}</div>}
      {items.map((n) => (
        <div key={n.id} className={`notice ${n.kind}`} role={n.kind === 'error' ? 'alert' : 'status'}>
          <span dir="auto">{n.text}</span>
          <button type="button" className="btn small ghost" onClick={() => dismiss(n.id)} aria-label={t('Dismiss')}>✕</button>
        </div>))}
    </div>
  )
}

// the words for an error: the server's message, or what went wrong on the way to it
export function errorText(e) {
  if (!e) return ''
  if (e instanceof ApiError) {
    if (e.status === 0) return t('No connection')
    if (e.status === 401) return t('You are signed out. Sign in again to continue.')
    if (e.status === 403) return e.message || t('Your account cannot do that.')
    if (e.status === 404) return t('Not found. It may have been removed, or the link is wrong.')
    if (e.status >= 500) return t('The server had a problem. Try again in a moment.')
  }
  return e.message || String(e)
}

// Inline: "<message> [Retry]". Replaces "Loading…" when a load fails; next to a form when a write fails.
export function ErrorBox({ error, onRetry, compact = false }) {
  if (!error) return null
  return (
    <div className={compact ? 'row err' : 'banner err-box'} role="alert">
      <span dir="auto">{errorText(error)}</span>
      {onRetry && <button type="button" className="btn small" onClick={onRetry}>{t('Retry')}</button>}
    </div>
  )
}

export function Loading({ text }) {
  return <div className="empty" role="status">{text || t('Loading…')}</div>
}

// loading / error / data in one place: <LoadState {...q}>{(data) => …}</LoadState>
export function LoadState({ data, error, loading, retry, children }) {
  if (data == null && error) return <ErrorBox error={error} onRetry={retry} />
  if (data == null && loading) return <Loading />
  if (data == null) return null
  return (
    <>
      {error && <ErrorBox error={error} onRetry={retry} />}
      {typeof children === 'function' ? children(data) : children}
    </>
  )
}

// Shown once per page to a viewer (role 'viewer'); the contributor controls themselves are hidden.
export function ReadOnlyNotice() {
  return (
    <div className="banner info readonly" role="note">
      {t('This account is read-only: everything can be read, but votes, corrections, ratings and comments are off. An admin can give it contributor access.')}
    </div>
  )
}
