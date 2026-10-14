import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { NavLink, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { api, setTracking, track } from './api'
import GapPanel from './components/GapPanel'
import ItemPanel from './components/ItemPanel'
import OutletPanel from './components/OutletPanel'
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
import { Invite, Login } from './pages/Auth'

const Ctx = createContext(null)
export const useApp = () => useContext(Ctx)

function readPref(k, d) { try { return localStorage.getItem(k) ?? d } catch { return d } }
function writePref(k, v) { try { localStorage.setItem(k, v) } catch { /* storage blocked */ } }

export default function App() {
  const [me, setMe] = useState(undefined)
  const loc = useLocation()
  useEffect(() => { api('/api/me').then(setMe).catch(() => setMe(null)) }, [])
  useEffect(() => { setTracking(!!me) }, [me])
  useEffect(() => { if (me) track('view', 'page', loc.pathname) }, [loc.pathname, me])

  if (me === undefined) return <div className="center-page muted">Loading…</div>
  if (!me) {
    return (
      <Routes>
        <Route path="/invite/:token" element={<Invite onDone={setMe} />} />
        <Route path="*" element={<Login onDone={setMe} />} />
      </Routes>
    )
  }
  return <Shell me={me} setMe={setMe} />
}

function Shell({ me, setMe }) {
  const [meta, setMeta] = useState(null)
  const [lang, setLangState] = useState(readPref('dw_lang', 'en'))
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
      return { ...f, lens: avail.includes(f.lens) ? f.lens : (avail[0] || 'audience'), week: m.latest_week }
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
  const setLang = (l) => { setLangState(l); writePref('dw_lang', l) }

  const value = useMemo(() => ({
    me, setMe, meta, lang, setLang, filters, setFilters, version, refresh: () => setVersion((v) => v + 1),
    openGap: (theme_id, region_id, ctx = {}) => { track('click', 'gap', `${theme_id}:${region_id}`, ctx); setPanel({ kind: 'gap', theme_id, region_id }) },
    openItem: (id) => { track('click', 'item', id); setPanel({ kind: 'item', id }) },
    openOutlet: (id) => { track('click', 'outlet', id); setPanel({ kind: 'outlet', id }) },
    openAdd: (preset = {}) => setPanel({ kind: 'add', preset }),
    closePanel: () => setPanel(null),
  }), [me, meta, lang, filters, version, setFilters, setMe])

  const logout = async () => { await api('/api/auth/logout', { method: 'POST' }); setMe(null); nav('/') }

  return (
    <Ctx.Provider value={value}>
      <div className="shell">
        <header className="topbar">
          <div className="brand"><span className="brand-mark" aria-hidden="true" />Desert Watch
            <span className="muted small" style={{ fontWeight: 400 }}>{meta?.country?.name_en}</span></div>
          <nav className="nav" aria-label="Main">
            <NavLink to="/" end>Map</NavLink>
            <NavLink to="/trends">Trends</NavLink>
            <NavLink to="/timeline">Timeline</NavLink>
            <NavLink to="/articles">Articles</NavLink>
            <NavLink to="/outlets">Outlets</NavLink>
            <NavLink to="/digest">Digest</NavLink>
            {me.role === 'admin' && <NavLink to="/admin">Admin{pending > 0 && <span className="pill flag" style={{ marginLeft: 4 }}>{pending}</span>}</NavLink>}
            <NavLink to="/me">Privacy</NavLink>
          </nav>
          <div className="who">
            {me.role !== 'viewer' && <button className="btn small primary" onClick={() => value.openAdd()}>+ Add article</button>}
            {me.role === 'viewer' && <span className="pill" title="Read-only account: an admin can give you contributor access">read-only</span>}
            <div className="seg" role="group" aria-label="Label language">
              <button aria-pressed={lang === 'en'} onClick={() => setLang('en')}>EN</button>
              <button aria-pressed={lang === 'ar'} onClick={() => setLang('ar')}>عربي</button>
            </div>
            <span>{me.display_name}</span>
            <button className="btn small ghost" onClick={logout}>Sign out</button>
          </div>
        </header>
        {!meta ? <div className="empty">Loading…</div> : (
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/trends" element={<Trends />} />
            <Route path="/outlets" element={<Outlets />} />
            <Route path="/admin" element={me.role === 'admin' ? <Admin /> : <Navigate to="/" />} />
            <Route path="/me" element={<Me />} />
            <Route path="/digest" element={<DigestPage />} />
            <Route path="/timeline" element={<Timeline />} />
            <Route path="/articles" element={<Articles />} />
            <Route path="*" element={<Navigate to="/" />} />
          </Routes>
        )}
        {meta && <PageFeedback />}
      </div>
      {!me.tracking_notice_ack && <TrackingNotice />}
      {panel && <div className="drawer-backdrop" onClick={value.closePanel} />}
      {panel?.kind === 'gap' && <GapPanel key={`${panel.theme_id}:${panel.region_id}`} themeId={panel.theme_id} regionId={panel.region_id} />}
      {panel?.kind === 'item' && <ItemPanel key={panel.id} id={panel.id} />}
      {panel?.kind === 'outlet' && <OutletPanel key={panel.id} id={panel.id} />}
      {panel?.kind === 'add' && <AddArticle preset={panel.preset} />}
    </Ctx.Provider>
  )
}
