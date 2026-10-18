// One GET and its state: {data, error, loading, refreshing, retry, setData}.
//   const { data, error, loading, retry } = useApi('/api/gap' + qs({ ... }), { deps: [version] })
// Every call has its own AbortController, cancelled when the path or a dep changes or the component
// goes away, so a slow answer never overwrites a newer one. While a refetch is in flight the old data
// stays (refreshing = true); a failure keeps it too and sets error, so a page can show what it has
// with an inline error and a Retry. `path` null skips the call (data stays null, loading false).
import { useCallback, useEffect, useRef, useState } from 'react'
import { api, isAbort } from '../api'

export function useApi(path, { deps = [], enabled = true } = {}) {
  const [state, setState] = useState({ data: null, error: null, loading: !!(path && enabled), refreshing: false })
  const [tick, setTick] = useState(0)
  const dataRef = useRef(null)
  useEffect(() => {
    if (!path || !enabled) { setState((s) => ({ ...s, loading: false, refreshing: false })); return undefined }
    const ac = new AbortController()
    setState((s) => ({ ...s, error: null, loading: dataRef.current == null, refreshing: dataRef.current != null }))
    api(path, { signal: ac.signal }).then((d) => {
      dataRef.current = d
      setState({ data: d, error: null, loading: false, refreshing: false })
    }).catch((e) => {
      if (isAbort(e)) return
      setState((s) => ({ ...s, error: e, loading: false, refreshing: false }))
    })
    return () => ac.abort()
  }, [path, enabled, tick, ...deps]) // eslint-disable-line react-hooks/exhaustive-deps
  const retry = useCallback(() => setTick((n) => n + 1), [])
  // a mutation's response can replace or patch the data without a round trip
  const setData = useCallback((next) => {
    setState((s) => {
      const d = typeof next === 'function' ? next(s.data) : next
      dataRef.current = d
      return { ...s, data: d }
    })
  }, [])
  return { ...state, retry, setData }
}
