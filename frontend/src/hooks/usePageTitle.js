// document.title per page: "Trends · Desert Watch". A page or a dialog passes its own name; the app
// name alone when nothing is passed. The last mounted caller wins, so a dialog over a page names the dialog.
import { useEffect } from 'react'

const APP = 'Desert Watch'

export function usePageTitle(title) {
  useEffect(() => {
    if (typeof document === 'undefined') return undefined
    const prev = document.title
    document.title = title ? `${title} · ${APP}` : APP // i18n-ok: the app name stays in both languages
    return () => { document.title = prev }
  }, [title])
}
