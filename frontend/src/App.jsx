import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { NavLink, Navigate, Route, Routes, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, setTracking, setUnauthorisedHandler, track } from './api'
import { getLang, pick, saveLang, setLang as applyLang, t } from './i18n'
import LangSwitch from './components/LangSwitch'
import GapPanel from './components/GapPanel'
import ItemPanel from './components/ItemPanel'
import OutletPanel from './components/OutletPanel'
import AddArticle from './components/AddArticle'
import TrackingNotice from './components/TrackingNotice'
import PageFeedback from './components/PageFeedback'
import { ErrorBox, Loading, NoticesProvider, ReadOnlyNotice } from './components/Notices'
import { useApi } from './hooks/useApi'
import { useFilters } from './hooks/useFilters'
import { useWide } from './hooks/useMedia'
import { addPath, articlePath, articlesPath, detailKind, filterSearch, gapParams, gapPath, idList, loginPath, outletPath, parentPath, parseId, safeNext } from './routes'
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

export default function App() {
  const [me, setMe] = useState(undefined)
  const [lang, setLangState] = useState(getLang())
  // switching language remounts the screens below, so every t() and every API text is fetched again
  const setLang = useCallback((l) => { applyLang(l); saveLang(l); setLangState(l) }, [])
  const loc = useLocation()
  const nav = useNavigate()
  // the first /api/me may say "not signed in": that is an answer, not a failure
  useEffect(() => { api('/api/me', { silent401: true }).then(setMe).catch(() => setMe(null)) }, [])
  // any later 401 means the session ended: clear the user and come back to this page after sign-in
  const locRef = useRef(loc); locRef.current = loc
  const meRef = useRef(me); meRef.current = me
  useEffect(() => {
    setUnauthorisedHandler(() => {
      if (!meRef.current) return
      meRef.current = null
      setMe(null)
      const l = locRef.current
      nav(loginPath(l.pathname + l.search), { replace: true })
    })
    return () => setUnauthorisedHandler(null)
  }, [nav])
  // tracking starts only once the notice has been acknowledged (the server drops events before that too)
  const tracking = !!me && !!me.tracking_notice_ack
  useEffect(() => { setTracking(tracking) }, [tracking])
  useEffect(() => { if (tracking) track('view', 'page', loc.pathname) }, [loc.pathname, tracking])
  // /api/meta once per app load (not again on every refresh or language switch); reloadMeta for admins who edit themes
  const metaQ = useApi(me ? '/api/meta' : null)

  if (me === undefined) return <div className="center-page"><Loading /></div>
  if (!me) {
    return (
      <NoticesProvider>
        <Routes key={lang}>
          <Route path="/invite/:token" element={<Invite onDone={setMe} lang={lang} setLang={setLang} />} />
          <Route path="*" element={<Login onDone={setMe} lang={lang} setLang={setLang} />} />
        </Routes>
      </NoticesProvider>
    )
  }
  return (
    <NoticesProvider>
      <Shell key={lang} me={me} setMe={setMe} lang={lang} setLang={setLang} metaQ={metaQ} />
    </NoticesProvider>
  )
}

// a plain, serialisable copy of a location, kept in history state as the page behind a dialog
const bare = (l) => ({ pathname: l.pathname, search: l.search || '', hash: l.hash || '' })

function Shell({ me, setMe, lang, setLang, metaQ }) {
  const meta = metaQ.data
  const [version, setVersion] = useState(0) // bump to refetch after feedback
  const nav = useNavigate()
  const loc = useLocation()
  const wide = useWide()
  const can = me.role !== 'viewer' // one flag: may vote, correct, rate, comment, add
  const locRef = useRef(loc); locRef.current = loc

  // A detail view (gap, article, outlet, add) sits over the page it was opened from; a shared link
  // has no such page, so its parent list stands in. From 900px up the page stays rendered behind the
  // dialog; below that the detail is the page.
  const kind = detailKind(loc.pathname)
  const background = kind ? (loc.state?.background ?? { pathname: parentPath(loc.pathname), search: '', hash: '' }) : null
  const pageLoc = background && wide ? background : loc
  const [filters, setFilters] = useFilters(meta, background ? background.search : loc.search)
  const carry = filterSearch(new URLSearchParams(pageLoc.search)) // lens and week follow the reader from page to page

  const pendingQ = useApi(me.role === 'admin' ? '/api/admin/users' : null, { deps: [version] })
  const pending = pendingQ.data ? pendingQ.data.filter((u) => u.status === 'pending').length : 0

  // open a detail view over the current page (or over the same page when one is already open)
  const open = useCallback((path, extra = {}) => {
    const l = locRef.current
    const k = detailKind(l.pathname)
    const bg = k ? (l.state?.background ?? { pathname: parentPath(l.pathname), search: '', hash: '' }) : bare(l)
    nav(path, { state: { ...extra, background: bg } })
  }, [nav])
  // close: back to the page behind when there is one in the history, else to the parent list
  const closePanel = useCallback(() => {
    const l = locRef.current
    if (l.state?.background) nav(-1)
    else nav(parentPath(l.pathname), { replace: true })
  }, [nav])

  const value = useMemo(() => ({
    me, setMe, meta, lang, setLang, filters, setFilters, version, can, refresh: () => setVersion((v) => v + 1), reloadMeta: metaQ.retry,
    openGap: (theme_id, region_id, ctx = {}) => { track('click', 'gap', `${theme_id}:${region_id}`, ctx); open(gapPath(theme_id, region_id, { lens: ctx.lens, week: ctx.week }), { from: ctx.from }) },
    openArticles: (spec) => { track('click', 'chart', spec.title, spec.query); nav(articlesPath(spec.query), { state: { title: spec.title, subtitle: spec.subtitle, note: spec.note, from: spec.from || 'chart' } }) },
    openItem: (id, ctx = {}) => { track('click', 'item', id, ctx); open(articlePath(id), { from: ctx.from }) },
    openOutlet: (id) => { track('click', 'outlet', id); open(outletPath(id)) },
    openAdd: (preset = {}) => open(addPath(preset)),
    closePanel,
  }), [me, meta, lang, setLang, filters, version, setFilters, setMe, can, open, closePanel, nav, metaQ.retry])

  const logout = async () => {
    try { await api('/api/auth/logout', { method: 'POST' }) } catch { /* the session is gone either way */ }
    setMe(null); nav('/')
  }
  const detailRoutes = (
    <>
      <Route path="/gaps/:themeId/:regionId" element={<GapRoute />} />
      <Route path="/articles/:id" element={<ArticleRoute />} />
      <Route path="/outlets/:id" element={<OutletRoute />} />
      <Route path="/add" element={<AddRoute />} />
    </>
  )

  return (
    <Ctx.Provider value={value}>
      <a className="skip-link" href="#main">{t('Skip to main content')}</a>
      <div className="shell">
        <header className="topbar">
          <div className="brand"><span className="brand-mark" aria-hidden="true" />Desert Watch
            <span className="muted small" style={{ fontWeight: 400 }}>{pick(meta?.country, 'name')}</span></div>
          <nav className="nav" aria-label={t('Main')}>
            <NavLink to={{ pathname: '/', search: carry }} end>{t('Map')}</NavLink>
            <NavLink to={{ pathname: '/trends', search: carry }}>{t('Trends')}</NavLink>
            <NavLink to="/timeline">{t('Timeline')}</NavLink>
            <NavLink to="/articles" end>{t('Articles')}</NavLink>
            <NavLink to={{ pathname: '/outlets', search: carry }} end>{t('Outlets')}</NavLink>
            <NavLink to="/digest">{t('Digest')}</NavLink>
            <NavLink to="/contribute">{t('Contribute')}</NavLink>
            {me.role === 'admin' && <NavLink to="/admin">{t('Admin')}{pending > 0 && <span className="pill flag" style={{ marginInlineStart: 4 }}>{pending}</span>}</NavLink>}
            <NavLink to="/me">{t('Privacy')}</NavLink>
          </nav>
          <div className="who">
            {can && <button className="btn small primary" onClick={() => value.openAdd()}>{t('+ Add article')}</button>}
            {!can && <span className="pill" title={t('Read-only account: an admin can give you contributor access')}>{t('read-only')}</span>}
            <LangSwitch lang={lang} setLang={setLang} />
            <span dir="auto">{me.display_name}</span>
            <button className="btn small ghost" onClick={logout}>{t('Sign out')}</button>
          </div>
        </header>
        <div id="main" className="main" tabIndex={-1}>
          {!can && <ReadOnlyNotice />}
          {!meta ? (
            <div className="page">{metaQ.error ? <ErrorBox error={metaQ.error} onRetry={metaQ.retry} /> : <Loading />}</div>
          ) : (
            <>
              <Routes location={pageLoc}>
                <Route path="/" element={<Overview />} />
                <Route path="/trends" element={<Trends />} />
                <Route path="/outlets" element={<Outlets />} />
                <Route path="/admin" element={me.role === 'admin' ? <Admin /> : <Navigate to="/" replace />} />
                <Route path="/me" element={<Me />} />
                <Route path="/digest" element={<DigestPage />} />
                <Route path="/timeline" element={<Timeline />} />
                <Route path="/articles" element={<Articles />} />
                <Route path="/contribute" element={<Contribute />} />
                <Route path="/login" element={<Navigate to={safeNext(new URLSearchParams(loc.search).get('next'))} replace />} />
                <Route path="/invite/:token" element={<Navigate to="/" replace />} />
                {detailRoutes}
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
              {background && wide && <Routes location={loc}>{detailRoutes}</Routes>}
            </>
          )}
        </div>
        {meta && <PageFeedback />}
      </div>
      {!me.tracking_notice_ack && <TrackingNotice />}
    </Ctx.Provider>
  )
}

// ---- detail routes: read the URL, check it, hand over to the panel -------------------------------

function GapRoute() {
  const { themeId, regionId } = useParams()
  const [sp] = useSearchParams()
  const loc = useLocation()
  const { meta } = useApp()
  const tid = parseId(themeId), rid = parseId(regionId)
  const { lens, week } = gapParams(sp, meta)
  const known = tid && rid && meta.themes.some((x) => x.id === tid) && meta.regions.some((r) => r.id === rid)
  // a view from the page it was opened on, or from a link (no page behind it)
  const from = loc.state?.background ? (loc.state.from || 'app') : 'url'
  useEffect(() => { if (known) track('view', 'gap', `${tid}:${rid}`, { from, lens: lens || undefined }) }, [known, tid, rid, from, lens])
  if (!known) return <Navigate to="/" replace />
  return <GapPanel key={`${tid}:${rid}:${lens}:${week}`} themeId={tid} regionId={rid} week={week} lens={lens} />
}

function ArticleRoute() {
  const id = parseId(useParams().id)
  if (!id) return <Navigate to="/articles" replace />
  return <ItemPanel key={id} id={id} />
}

function OutletRoute() {
  const id = parseId(useParams().id)
  if (!id) return <Navigate to="/outlets" replace />
  return <OutletPanel key={id} id={id} />
}

function AddRoute() {
  const [sp] = useSearchParams()
  const { can } = useApp()
  if (!can) return <Navigate to="/" replace />
  return <AddArticle preset={{ theme_ids: idList(sp.get('theme')), region_ids: idList(sp.get('region')) }} />
}
