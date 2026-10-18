// A write with its busy state and a visible error:
//   const vote = useMutation((v) => api('/api/gap/vote', { method: 'POST', body: ... }), { onSuccess: reload })
//   <button disabled={vote.busy} onClick={() => vote.run('real')}>…</button>  and an ErrorBox for vote.error
// run() resolves with the response, or with undefined when the call failed (the error is in `error`),
// so a caller never needs its own try/catch to keep the page alive.
import { useCallback, useEffect, useRef, useState } from 'react'
import { isAbort } from '../api'

export function useMutation(fn, { onSuccess } = {}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const alive = useRef(true)
  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])
  const run = useCallback(async (...args) => {
    setBusy(true); setError(null)
    try {
      const r = await fn(...args)
      onSuccess?.(r, ...args)
      return r
    } catch (e) {
      if (!isAbort(e) && alive.current) setError(e)
      return undefined
    } finally {
      if (alive.current) setBusy(false)
    }
  }, [fn, onSuccess])
  const clearError = useCallback(() => setError(null), [])
  return { run, busy, error, clearError }
}
