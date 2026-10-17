import { useEffect, useRef, useState } from 'react'
import { getLang, t } from '../i18n'

const N_ = (s) => s // marks English for the catalogue; translated with t() when shown

export function useSize(ref, fallback = 800) {
  const [w, setW] = useState(fallback)
  useEffect(() => {
    if (!ref.current) return
    const ro = new ResizeObserver(([e]) => setW(Math.max(260, Math.floor(e.contentRect.width))))
    ro.observe(ref.current)
    return () => ro.disconnect()
  }, [ref])
  return w
}

export function useTooltip() {
  const [tip, setTip] = useState(null)
  const show = (evt, content, container) => {
    const box = container.getBoundingClientRect()
    let x = evt.clientX - box.left + 14
    let y = evt.clientY - box.top + 14
    if (x > box.width - 290) x = Math.max(4, x - 300)
    setTip({ x, y, content })
  }
  // left/top stay physical: x and y are measured from the pointer, in screen coordinates
  const node = tip ? <div className="tooltip" style={{ left: tip.x, top: tip.y }} role="status">{tip.content}</div> : null
  return { show, hide: () => setTip(null), node }
}

// Hatch pattern for "insufficient evidence" (texture = never colour-alone).
export function HatchDefs({ id = 'hatch' }) {
  return (
    <defs>
      <pattern id={id} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
        <rect width="6" height="6" fill="var(--surface)" />
        <line x1="0" y1="0" x2="0" y2="6" stroke="var(--hatch)" strokeWidth="1.5" />
      </pattern>
    </defs>
  )
}

// Export an SVG node (with computed colours inlined) plus a caption with source + method note.
export function exportSvg(svgEl, { title, caption, filename = 'desert-watch-chart', format = 'svg' }) {
  const clone = svgEl.cloneNode(true)
  const vb = svgEl.viewBox.baseVal
  const w = vb && vb.width ? vb.width : svgEl.clientWidth
  const h = vb && vb.height ? vb.height : svgEl.clientHeight
  const extra = 64
  // inline resolved CSS variables so the file renders standalone
  const src = svgEl.querySelectorAll('*')
  clone.querySelectorAll('*').forEach((n, i) => {
    const cs = getComputedStyle(src[i])
    for (const p of ['fill', 'stroke', 'opacity', 'font-size', 'font-family', 'font-weight', 'stroke-width', 'fill-opacity', 'stroke-opacity']) {
      const v = cs.getPropertyValue(p)
      if (v) n.style.setProperty(p, v)
    }
  })
  const bg = getComputedStyle(document.documentElement).getPropertyValue('--surface').trim() || '#fff'
  const ink = getComputedStyle(document.documentElement).getPropertyValue('--ink-2').trim() || '#333'
  const ns = 'http://www.w3.org/2000/svg'
  // in Arabic the title and the source note run right to left from the right edge; the chart keeps its geometry
  const rtl = getLang() === 'ar'
  const place = (el, y) => {
    el.setAttribute('x', rtl ? w - 8 : 8); el.setAttribute('y', y)
    if (rtl) el.setAttribute('direction', 'rtl')
  }
  const wrap = document.createElementNS(ns, 'svg')
  wrap.setAttribute('xmlns', ns)
  wrap.setAttribute('viewBox', `0 0 ${w} ${h + extra + 28}`)
  wrap.setAttribute('width', w)
  wrap.setAttribute('height', h + extra + 28)
  const rect = document.createElementNS(ns, 'rect')
  rect.setAttribute('width', '100%'); rect.setAttribute('height', '100%'); rect.setAttribute('fill', bg)
  wrap.appendChild(rect)
  const head = document.createElementNS(ns, 'text') // not 't': that name is the translation function
  place(head, 20); head.setAttribute('font-size', 15); head.setAttribute('font-weight', 600)
  head.setAttribute('fill', ink); head.setAttribute('font-family', 'system-ui, sans-serif'); head.textContent = title // i18n-ok: CSS font list
  wrap.appendChild(head)
  const g = document.createElementNS(ns, 'g')
  g.setAttribute('transform', 'translate(0,28)')
  clone.removeAttribute('class')
  g.appendChild(clone)
  wrap.appendChild(g)
  caption.split('\n').forEach((line, i) => {
    const c = document.createElementNS(ns, 'text')
    place(c, h + 28 + 22 + i * 15); c.setAttribute('font-size', 11)
    c.setAttribute('fill', ink); c.setAttribute('font-family', 'system-ui, sans-serif'); c.textContent = line // i18n-ok: CSS font list
    wrap.appendChild(c)
  })
  const xml = new XMLSerializer().serializeToString(wrap)
  const download = (href, ext) => {
    const a = document.createElement('a'); a.href = href; a.download = `${filename}.${ext}`; a.click()
  }
  if (format === 'svg') {
    const url = URL.createObjectURL(new Blob([xml], { type: 'image/svg+xml' }))
    download(url, 'svg'); setTimeout(() => URL.revokeObjectURL(url), 2000)
    return
  }
  const img = new Image()
  img.onload = () => {
    const scale = 2
    const canvas = document.createElement('canvas')
    canvas.width = w * scale; canvas.height = (h + extra + 28) * scale
    const ctx = canvas.getContext('2d'); ctx.scale(scale, scale); ctx.drawImage(img, 0, 0)
    download(canvas.toDataURL('image/png'), 'png')
  }
  img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(xml) // i18n-ok: data URL prefix
}

export function ExportMenu({ svgRef, title, caption, filename }) {
  return (
    <span className="row">
      <button className="btn small ghost" onClick={() => exportSvg(svgRef.current, { title, caption, filename, format: 'svg' })} title={t('Download SVG with source and method note')}>{'SVG'}</button>
      <button className="btn small ghost" onClick={() => exportSvg(svgRef.current, { title, caption, filename, format: 'png' })} title={t('Download PNG with source and method note')}>{'PNG'}</button>
    </span>
  )
}

export function useLatest(value) {
  const r = useRef(value)
  r.current = value
  return r
}

// Theme label without its group prefix ("Gender: violence…" -> "violence…"); the group is shown
// as a heading row instead.
export function themeLabel(t, lang = 'en') {
  const name = (lang === 'ar' ? t.name_ar : t.name_en) || t.name_en
  return t.group ? name.replace(/^[^:：]+[:：]\s*/, '') : name
}

// Fit a label into maxPx using canvas text measurement; adds an ellipsis when it must cut.
let _ctx = null
export function fitLabel(text, maxPx, font = '12px system-ui, sans-serif') {
  if (!text) return ''
  if (!_ctx) _ctx = document.createElement('canvas').getContext('2d')
  _ctx.font = font
  if (_ctx.measureText(text).width <= maxPx) return text
  let lo = 0, hi = text.length
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1
    if (_ctx.measureText(text.slice(0, mid) + '…').width <= maxPx) lo = mid
    else hi = mid - 1
  }
  return text.slice(0, Math.max(1, lo)).trimEnd() + '…'
}

// Theme group heading ('gender' -> 'Gender'); a group with no entry here shows its code, capitalised.
const GROUPS = { gender: N_('Gender') }
export function groupLabel(g) {
  return GROUPS[g] ? t(GROUPS[g]) : g[0].toUpperCase() + g.slice(1)
}

// Rows grouped by theme.group: [{header: 'Gender'} | {theme}] in display order (ungrouped first).
export function groupedRows(themes) {
  const plain = themes.filter((t) => !t.group)
  const groups = [...new Set(themes.filter((t) => t.group).map((t) => t.group))]
  const rows = plain.map((t) => ({ theme: t }))
  for (const g of groups) {
    rows.push({ header: groupLabel(g) })
    themes.filter((t) => t.group === g).forEach((t) => rows.push({ theme: t }))
  }
  return rows
}
