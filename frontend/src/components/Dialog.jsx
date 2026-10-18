// The one dialog. From 900px up it is a panel over the page behind (a side drawer, or a centred box
// with variant="modal"); below that it is a full page with a sticky Back bar, so a phone never shows
// a panel it cannot close. Escape, the close button, the backdrop and the browser's Back all go through
// onClose (the app navigates back, or to the parent list when there is no page behind). Focus moves to
// the heading on open and returns to the trigger on close; Tab cycles inside while it is a panel.
// mode="modal" keeps the panel form at every width (the tracking notice, which blocks the app anyway).
import { useEffect, useId, useRef } from 'react'
import { useWide } from '../hooks/useMedia'
import { t } from '../i18n'

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])' // i18n-ok: a CSS selector

export default function Dialog({ title, subtitle, actions, onClose, backdropCloses = true, mode = 'auto', variant = 'drawer', children, className = '' }) {
  const wide = useWide()
  const asPage = mode === 'auto' && !wide
  const id = useId()
  const box = useRef(null)
  const head = useRef(null)

  // focus: to the heading on open, back to the trigger on close
  useEffect(() => {
    const prev = typeof document !== 'undefined' ? document.activeElement : null
    if (asPage) window.scrollTo(0, 0) // a page: start at its top, not where the list behind was scrolled to
    const raf = requestAnimationFrame(() => head.current?.focus({ preventScroll: asPage }))
    return () => {
      cancelAnimationFrame(raf)
      if (prev && prev.isConnected && typeof prev.focus === 'function') prev.focus()
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // the page behind a panel does not scroll
  useEffect(() => {
    if (asPage) return undefined
    document.body.classList.add('dialog-open')
    return () => document.body.classList.remove('dialog-open')
  }, [asPage])

  const onKeyDown = (e) => {
    if (e.key === 'Escape' && onClose) { e.stopPropagation(); onClose(); return }
    if (e.key !== 'Tab' || asPage || !box.current) return
    const els = [...box.current.querySelectorAll(FOCUSABLE)].filter((el) => el.offsetParent !== null || el === head.current)
    if (!els.length) { e.preventDefault(); return }
    const first = els[0], last = els[els.length - 1]
    if (e.shiftKey && (document.activeElement === first || document.activeElement === head.current)) { e.preventDefault(); last.focus() }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
  }
  const onBackdrop = () => {
    if (!onClose) return
    if (typeof backdropCloses === 'function' ? backdropCloses() : backdropCloses) onClose()
  }

  const heading = (
    <div className="dialog-head">
      <div style={{ minWidth: 0, flex: 1 }}>
        {subtitle && <div className="small muted">{subtitle}</div>}
        <h2 id={id} ref={head} tabIndex={-1} className="dialog-title">{title}</h2>
      </div>
      <div className="row" style={{ flexWrap: 'nowrap', flex: 'none' }}>
        {actions}
        {onClose && !asPage && <button type="button" className="btn ghost" onClick={onClose} aria-label={t('Close')}>✕</button>}
      </div>
    </div>
  )

  if (asPage) {
    return (
      <main className={`page dialog-page ${className}`} aria-labelledby={id} ref={box} onKeyDown={onKeyDown}>
        <div className="dialog-bar">
          {onClose && <button type="button" className="btn small" onClick={onClose}>{t('← Back')}</button>}
          {heading}
        </div>
        <section className="card">{children}</section>
      </main>
    )
  }
  return (
    <>
      <div className="drawer-backdrop" onClick={onBackdrop} />
      <aside className={`${variant === 'modal' ? 'modal' : 'drawer'} ${className}`} role="dialog" aria-modal="true" aria-labelledby={id} ref={box} onKeyDown={onKeyDown}>
        {heading}
        {children}
      </aside>
    </>
  )
}
