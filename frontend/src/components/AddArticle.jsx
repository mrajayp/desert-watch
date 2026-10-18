import { useState } from 'react'
import { api } from '../api'
import { useApp } from '../App'
import { useMutation } from '../hooks/useMutation'
import { usePageTitle } from '../hooks/usePageTitle'
import { pick, t } from '../i18n'
import Dialog from './Dialog'
import { ErrorBox } from './Notices'

// Add an article we missed: /add?theme=&region=. A tap on the backdrop closes it only while it is empty.
export default function AddArticle({ preset = {} }) {
  const { meta, closePanel, refresh } = useApp()
  const [url, setUrl] = useState('')
  const [meta2, setMeta2] = useState(null)
  const [title, setTitle] = useState('')
  const [themes, setThemes] = useState(preset.theme_ids || [])
  const [regions, setRegions] = useState(preset.region_ids || [])
  const [done, setDone] = useState(null)
  const toggle = (arr, set, v) => set(arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v])
  usePageTitle(t('Add an article we missed'))

  const preview = useMutation(() => api('/api/items/preview', { method: 'POST', body: { url } }),
    { onSuccess: (m) => { setMeta2(m); setTitle(m.title || '') } })
  const fetchPreview = async () => {
    const m = await preview.run()
    if (m === undefined) setMeta2({}) // the page could not be read: the title can still be typed
  }
  const save = useMutation(() => api('/api/items', { method: 'POST', body: { url, title: title || null, lang: meta2?.lang || null, published: meta2?.published || null, theme_ids: themes, region_ids: regions } }),
    { onSuccess: (it) => { setDone(it); refresh() } })
  const busy = preview.busy || save.busy
  const hasContent = !!(url || title || meta2)
  return (
    <Dialog variant="modal" title={t('Add an article we missed')} onClose={closePanel} backdropCloses={() => !hasContent || !!done}>
      <p className="small muted">{t('Counts as coverage straight away and teaches the topic matcher. Good for Facebook pages, where we only see the posts Google News indexes.')}</p>
      {done ? (
        <div>
          <p>{t('Added:')} <b dir="auto">{done.title}</b> ({done.outlet?.name}).</p>
          <div className="row"><button className="btn" onClick={() => { setDone(null); setUrl(''); setMeta2(null); setTitle('') }}>{t('Add another')}</button>
            <button className="btn primary" onClick={closePanel}>{t('Done')}</button></div>
        </div>
      ) : (
        <div className="form">
          <label>{t('Link')}
            <div className="row" style={{ flexWrap: 'nowrap' }}>
              <input type="url" value={url} onChange={(e) => setUrl(e.target.value)} style={{ flex: 1 }}
                placeholder="https://…" // i18n-ok: a URL pattern, the same in both languages
              />
              <button className="btn" disabled={!url || busy} onClick={fetchPreview}>{t('Fetch')}</button>
            </div>
          </label>
          {preview.error && <p className="err">{preview.error.message} {t('You can still type the title yourself.')}</p>}
          {meta2 && (
            <>
              <label>{t('Title')}<input type="text" dir="auto" value={title} onChange={(e) => setTitle(e.target.value)} /></label>
              {meta2.site_name && <div className="small muted">{meta2.site_name} · {meta2.domain} · {meta2.lang || t('language?')} · {meta2.published?.slice(0, 10) || t('date unknown')}</div>}
              <div><div className="small">{t('Topics')}</div><div className="chips">{meta.themes.map((th) =>
                <button key={th.id} className="chip" aria-pressed={themes.includes(th.id)} onClick={() => toggle(themes, setThemes, th.id)}>{pick(th, 'name')}</button>)}</div></div>
              <div><div className="small">{t('Places (optional)')}</div><div className="chips">{meta.regions.filter((r) => r.level === 'district').map((r) =>
                <button key={r.id} className="chip" aria-pressed={regions.includes(r.id)} onClick={() => toggle(regions, setRegions, r.id)}>{pick(r, 'name')}</button>)}</div></div>
              <div className="row"><span className="spacer" /><button className="btn primary" disabled={busy || !themes.length || !title} onClick={() => save.run()}>{t('Add article')}</button></div>
            </>)}
          {save.error && <ErrorBox error={save.error} compact />}
        </div>)}
    </Dialog>
  )
}
