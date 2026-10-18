// "Copy link": the address of this gap, article or outlet onto the clipboard, with a fallback for
// browsers that give no clipboard API on a plain http page.
import { useEffect, useRef, useState } from 'react'
import { track } from '../api'
import { t } from '../i18n'

function copyText(text) {
  if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) return navigator.clipboard.writeText(text)
  return new Promise((resolve, reject) => {
    const ta = document.createElement('textarea')
    ta.value = text; ta.setAttribute('readonly', ''); ta.style.position = 'fixed'; ta.style.opacity = '0'
    document.body.appendChild(ta); ta.select()
    let ok = false
    try { ok = document.execCommand('copy') } catch { ok = false }
    document.body.removeChild(ta)
    ok ? resolve() : reject(new Error('copy failed')) // i18n-ok: not shown
  })
}

export default function CopyLink({ path, objectType, objectKey }) {
  const [state, setState] = useState(null) // 'done' | 'failed'
  const timer = useRef(null)
  useEffect(() => () => clearTimeout(timer.current), [])
  const copy = async () => {
    const url = window.location.origin + path
    try { await copyText(url); setState('done') } catch { setState('failed') }
    track('click', 'share', objectKey ?? path, { object_type: objectType })
    clearTimeout(timer.current)
    timer.current = setTimeout(() => setState(null), 2500)
  }
  return (
    <button type="button" className="btn small ghost" onClick={copy} aria-live="polite" title={t('Copy a link to this view')}>
      {state === 'done' ? t('Link copied') : state === 'failed' ? t('Could not copy') : t('Copy link')}
    </button>
  )
}
