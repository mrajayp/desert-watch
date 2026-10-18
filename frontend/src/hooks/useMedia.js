// Does the viewport match a media query right now, kept up to date. The detail views are a dialog
// over the page from WIDE up and a full page with a Back bar below it.
import { useEffect, useState } from 'react'

export const WIDE = '(min-width: 900px)'

export function useMedia(query) {
  const get = () => (typeof window !== 'undefined' && window.matchMedia ? window.matchMedia(query).matches : true)
  const [on, setOn] = useState(get)
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return undefined
    const mq = window.matchMedia(query)
    const h = () => setOn(mq.matches)
    h()
    mq.addEventListener('change', h)
    return () => mq.removeEventListener('change', h)
  }, [query])
  return on
}

export const useWide = () => useMedia(WIDE)
