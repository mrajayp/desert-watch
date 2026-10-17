import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { NavLink, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { api, setTracking, track } from './api'
import { getLang, pick, saveLang, setLang as applyLang, t } from './i18n'
import LangSwitch from './components/LangSwitch'
import { lensWeek } from './lensWeek'
import GapPanel from './components/GapPanel'
import ItemPanel from './components/ItemPanel'
import OutletPanel from './components/OutletPanel'
import ArticlesPanel from './components/ArticlesPanel'
import AddArticle from './components/AddArticle'
import TrackingNotice from './components/TrackingNotice'
import PageFeedback from './components/PageFeedback'
import Overview from './pages/Overview'
import Trends from './pages/Trends'
import Outlets from './pages/Outlets'
import Admin from './pages/Admin'
import Me from './pages/Me'
import DigestPage from './pages/Digest'
import Timeline from './pages/Timeline'
import Articles from './pages/Articles'
import Contribute from './pages/Contribute'
import { Invite, Login } from './pages/Auth'

const Ctx = createContext(null)
export const useApp = () => useContext(Ctx)

function readPref(k, d) { try { return localStorage.getItem(k) ?? d } catch { return d } }
function writePref(k, v) { try { localStorage.setItem(k, v) } catch { /* storage blocked */ } }

export default function App() {
  const [me, setMe] = useState(undefined)
  const [lang, setLangState] = useState(getLang())
  // switching language remounts the screens below, so every t() and every API text is fetched again
  const setLang = useCallback((l) => { applyLang(l); saveLang(l); setLangState(l) }, [])
  const loc = useLocation()
  useEffect(() => { api('/api/me').then(setMe).catch(() => setMe(null)) }, [])
  useEffect(() => { setTracking(!!me) }, [me])
  useEffect(() => { if (me) track('view', 'page', loc.pathname) }, [loc.pathname, me])

  if (me === undefined) return <div className="center-page muted">{t('Loading…')}</div>
  if (!me) {
    return (
      <Routes key={lang}>
        <Route path="/invite/:token" element={<Invite onDone={setMe} lang={lang} setLang={setLang} />} />
        <Route path="*" element={<Login onDone={setMe} lang={lang} setLang={setLang} />} />
      </Routes>
    )
  }
  return <Shell key={lang} me={me} setMe={setMe} lang={lang} setLang={setLang} />
}

function Shell({ me, setMe, lang, setLang }) {
  const [meta, setMeta] = useState(null)
  const [filters, setFiltersState] = useState({ lens: readPref('dw_lens', 'audience'), week: null, themeId: '', colorBy: readPref('dw_color', 'scope') })
  const [panel, setPanel] = useState(null) // {kind, ...}
  const [version, setVersion] = useState(0) // bump to refetch after feedback
  const nav = useNavigate()
  const [pending, setPending] = useState(0)
  useEffect(() => {
    if (me.role !== 'admin') return
    api('/api/admin/users').then((us) => setPending(us.filter((u) => u.status === 'pending').length)).catch(() => {})
  }, [me.role, version])

  useEffect(() => { api('/api/meta').then((m) => {
    setMeta(m)
    setFiltersState((f) => {
      const avail = m.lenses.filter((l) => l.available).map((l) => l.key)
      const lens = avail.includes(f.lens) ? f.lens : (avail[0] || 'audience')
      return { ...f, lens, week: lensWeek(m, lens) }
    })
  }) }, [version])

  const setFilters = useCallback((patch) => {
    setFiltersState((f) => {
      const n = { ...f, ...patch }
      if (patch.lens) writePref('dw_lens', patch.lens)
      if (patch.colorBy) writePref('dw_color', patch.colorBy)
      track('filter', 'page', location.pathname, patch)
      return n
    })
  }, [])
  const value = useMemo(() => ({
    me, setMe, meta, lang, setLang, filters, setFilters, version, refresh: () => setVersion((v) => v + 1),
    openGap: (theme_id, region_id, ctx = {}) => { track('click', 'gap', `${theme_id}:${region_id}`, ctx); setPanel({ kind: 'gap', theme_id, region_id, week: ctx.week, lens: ctx.lens }) },
    openArticles: (spec) => { track('click', 'chart', spec.title, spec.query); setPanel({ kind: 'articles', ...spec }) },
    openItem: (id) => { track('click', 'item', id); setPanel({ kind: 'item', id }) },
    openOutlet: (id) => { track('click', 'outlet', id); setPanel({ kind: 'outlet', id }) },
    openAdd: (preset = {}) => setPanel({ kind: 'add', preset }),
    closePanel: () => setPanel(null),
  }), [me, meta, lang, setLang, filters, version, setFilters, setMe])

  const logout = async () => { await api('/api/auth/logout', { method: 'POST' }); setMe(null); nav('/') }

  return (
    <Ctx.Provider value={value}>
      <div className="shell">
        <header className="topbar">
          <div className="brand"><span className="brand-mark" aria-hidden="true" />Desert Watch
            <span className="muted small" style={{ fontWeight: 400 }}>{pick(meta?.country, 'name')}</span></div>
          <nav className="nav" aria-label={t('Main')}>
            <NavLink to="/" end>{t('Map')}</NavLink>
            <NavLink to="/trends">{t('Trends')}</NavLink>
            <NavLink to="/timeline">{t('Timeline')}</NavLink>
            <NavLink to="/articles">{t('Articles')}</NavLink>
            <NavLink to="/outlets">{t('Outlets')}</NavLink>
            <NavLink to="/digest">{t('Digest')}</NavLink>
            <NavLink to="/contribute">{t('Contribute')}</NavLink>
            {me.role === 'admin' && <NavLink to="/admin">{t('Admin')}{pending > 0 && <span className="pill flag" style={{ marginInlineStart: 4 }}>{pending}</span>}</NavLink>}
            <NavLink to="/me">{t('Privacy')}</NavLink>
          </nav>
          <div className="who">
            {me.role !== 'viewer' && <button className="btn small primary" onClick={() => value.openAdd()}>{t('+ Add article')}</button>}
            {me.role === 'viewer' && <span className="pill" title={t('Read-only account: an admin can give you contributor access')}>{t('read-only')}</span>}
            <LangSwitch lang={lang} setLang={setLang} />
            <span dir="auto">{me.display_name}</span>
            <button className="btn small ghost" onClick={logout}>{t('Sign out')}</button>
          </div>
        </header>
        {!meta ? <div className="empty">{t('Loading…')}</div> : (
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/trends" element={<Trends />} />
            <Route path="/outlets" element={<Outlets />} />
            <Route path="/admin" element={me.role === 'admin' ? <Admin /> : <Navigate to="/" />} />
            <Route path="/me" element={<Me />} />
            <Route path="/digest" element={<DigestPage />} />
            <Route path="/timeline" element={<Timeline />} />
            <Route path="/articles" element={<Articles />} />
            <Route path="/contribute" element={<Contribute />} />
            <Route path="*" element={<Navigate to="/" />} />
          </Routes>
        )}
        {meta && <PageFeedback />}
      </div>
      {!me.tracking_notice_ack && <TrackingNotice />}
      {panel && <div className="drawer-backdrop" onClick={value.closePanel} />}
      {panel?.kind === 'gap' && <GapPanel key={`${panel.theme_id}:${panel.region_id}:${panel.week}`} themeId={panel.theme_id} regionId={panel.region_id} week={panel.week} lens={panel.lens} />}
      {panel?.kind === 'articles' && <ArticlesPanel key={JSON.stringify(panel.query)} title={panel.title} subtitle={panel.subtitle} query={panel.query} note={panel.note} />}
      {panel?.kind === 'item' && <ItemPanel key={panel.id} id={panel.id} />}
      {panel?.kind === 'outlet' && <OutletPanel key={panel.id} id={panel.id} />}
      {panel?.kind === 'add' && <AddArticle preset={panel.preset} />}
    </Ctx.Provider>
  )
}
