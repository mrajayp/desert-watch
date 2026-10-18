// The page filters (lens, week, theme, colour) live in the URL, so a link carries them and a reload
// keeps them. localStorage only supplies the default when a parameter is absent, and is written only
// when the person touches the lens or the colour control (never by a view that opens a gap at its own
// lens and week). setFilters replaces the history entry, so Back still leaves the page.
// `search` is the query string of the page (the one behind an open dialog, not the dialog's own).
import { useCallback, useMemo } from 'react'
import { useLocation, useSearchParams } from 'react-router-dom'
import { track } from '../api'
import { DIMENSIONS } from '../charts/scales'
import { applyFilters, readFilters } from '../routes'

function readPref(k, d) { try { return localStorage.getItem(k) ?? d } catch { return d } }
function writePref(k, v) { try { localStorage.setItem(k, v) } catch { /* storage blocked */ } }

export function useFilters(meta, search) {
  const [, setSp] = useSearchParams()
  const loc = useLocation()
  const sp = useMemo(() => new URLSearchParams(search || ''), [search])
  const filters = useMemo(() => readFilters(sp, meta, { lens: readPref('dw_lens', null), colorBy: readPref('dw_color', null) }, Object.keys(DIMENSIONS)),
    [sp, meta])
  const setFilters = useCallback((patch) => {
    if (patch.lens) writePref('dw_lens', patch.lens)
    if (patch.colorBy) writePref('dw_color', patch.colorBy)
    track('filter', 'page', loc.pathname, patch)
    setSp((prev) => applyFilters(prev, patch), { replace: true })
  }, [setSp, loc.pathname])
  return [filters, setFilters]
}
