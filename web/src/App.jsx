import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, api, setUrlCase, urlOptions } from './api.js'
import { Viewer } from './viewer/Viewer.js'
import { useScene } from './scene/useScene.js'
import { initialAppearance, initialRequest } from './scene/state.js'
import { TopBar } from './ui/TopBar.jsx'
import { SidePane } from './ui/SidePane.jsx'
import { BottomBar } from './ui/BottomBar.jsx'
import { Busy, Hud, Legend } from './ui/overlays.jsx'
import { StartScreen } from './ui/StartScreen.jsx'
import { useShortcuts } from './ui/shortcuts.js'
import { applyScene, emptyViews, importViews, readViews, sceneFrom } from './views/document.js'
import { localStore } from './views/localStore.js'

/*
 * The composition root. It owns the two state objects (see scene/state.js) and
 * the one imperative Viewer, and it is the only place the two meet.
 *
 * Note what is NOT here: any three.js. React drives the scene through Viewer
 * methods, so the UI has no opinion about how pixels are made -- which is what
 * would let react-three-fiber take over the viewer later without touching a
 * single control.
 */

export default function App() {
  const url = useRef(urlOptions()).current
  const stageRef = useRef(null)
  const viewerRef = useRef(null)
  const lutCache = useRef(new Map())

  const [meta, setMeta] = useState(null)
  const [request, setRequestState] = useState(null)
  const [appearance, setAppearanceState] = useState(() => ({
    ...initialAppearance(url.theme), activeTool: 'cutplane',
  }))
  const [lut, setLut] = useState(null)
  // The server's range for a named field, kept apart from appearance.range so
  // the patch field can show it whatever auto range says.
  const [dataRange, setDataRange] = useState(null)
  const [stats, setStats] = useState({ fps: 0, triangles: 0, calls: 0 })
  // Whether the streamlines on the GPU actually carry travel time. Polled with
  // the stats rather than derived from state, because it depends on what the
  // server returned, not on what was asked for -- an empty stream part cannot
  // be animated however the request looked.
  const [canAnimate, setCanAnimate] = useState(false)

  // Which case to open: an id or a name. From ?case= (the cockpit passes a
  // directory name), else chosen on the start screen or in the switcher.
  const [caseKey, setCaseKey] = useState(url.case || null)
  // True from a case switch until its /api/meta answers; a zip unpacks in that
  // request, so the old case would otherwise sit there with no sign of work.
  const [opening, setOpening] = useState(false)
  const [config, setConfig] = useState(null)
  const [entries, setEntries] = useState([])
  const [entriesLoading, setEntriesLoading] = useState(true)
  // The start screen: shown when there is no case to open, or the one asked
  // for does not exist (then with the server's reason as `notice`).
  const [start, setStart] = useState({ show: false, notice: null })
  // The open case's saved scenes and camera slots, and the one notice the scene
  // section shows (openspec scenes-and-cameras A4, A10).
  const [views, setViews] = useState(emptyViews)
  const [viewsNotice, setViewsNotice] = useState(null)
  // Set when a scene load sets the isosurface's values, so the reseed below does
  // not overwrite them; holds the field identity the scene brings.
  const keepContour = useRef(null)
  // Read by the __viz.state test hook, which is installed once.
  const stateRef = useRef(null)
  stateRef.current = { request, appearance, views }

  const setRequest = useCallback((patch) => {
    setRequestState((r) => (typeof patch === 'function' ? patch(r) : { ...r, ...patch }))
  }, [])
  const setAppearance = useCallback((patch) => {
    setAppearanceState((a) => ({ ...a, ...patch }))
  }, [])

  // The domain diagonal, so tube widths scale with the case instead of being a
  // fixed number that is invisible in a hall and absurd in a duct.
  const domain = meta
    ? Math.hypot(meta.bounds[1] - meta.bounds[0],
                 meta.bounds[3] - meta.bounds[2],
                 meta.bounds[5] - meta.bounds[4]) || 1
    : 1

  // -- the viewer ------------------------------------------------------

  useEffect(() => {
    const viewer = new Viewer(stageRef.current)
    viewerRef.current = viewer
    // Test hooks for tests/check_client.py -- see Viewer.grab for why the pixel
    // count is computed in the browser rather than shipped out.
    window.__viz = {
      grab: () => viewer.grab(),
      camera: () => viewer.camera_state(),
      stats: () => viewer.stats(),
      comets: () => viewer.comet_state(),
      // Lets a test (or a tuning sweep) drive the animation's shape directly,
      // including the two knobs the UI keeps fixed at their tuned defaults.
      tuneComets: (o) => viewer.setComets(o),
      partInfo: (name) => viewer.partInfo(name),
      streamSpans: () => viewer.streamSpans(),
      state: () => stateRef.current,
    }
    return () => { viewer.dispose(); viewerRef.current = null }
  }, [])

  useEffect(() => {
    const id = setInterval(() => {
      const viewer = viewerRef.current
      if (!viewer) return
      setStats(viewer.stats())
      setCanAnimate(viewer.canAnimateStreams())
    }, 500)
    return () => clearInterval(id)
  }, [])

  // -- cases and the start screen ----------------------------------------

  // Both cheap -- neither opens a case -- so they are fetched up front even when
  // ?case= is given: the switcher lists the same entries as the start screen.
  const refreshEntries = useCallback(() => {
    setEntriesLoading(true)
    return api.caseEntries()
      .then((list) => { setEntries(list); return list })
      .catch(() => { setEntries([]); return [] })
      .finally(() => setEntriesLoading(false))
  }, [])

  // Open a case by id, and put the id in the address bar so a reload or a
  // bookmark reopens it.
  const openCase = useCallback((id) => {
    setUrlCase(id)
    setCaseKey(id)
    setStart({ show: false, notice: null })
  }, [])

  // "All cases" in the side pane: the start screen over the open case, which
  // stays open (openspec ice-project-zips, D10).
  const showCases = useCallback(() => {
    refreshEntries()
    setStart({ show: true, notice: null })
  }, [refreshEntries])

  // Each time the start screen shows, so the cache size is current (D6).
  const refreshConfig = useCallback(() => api.config().then(setConfig).catch(() => {}), [])
  useEffect(() => { if (start.show) refreshConfig() }, [start.show, refreshConfig])

  // A folder added in local mode: new cases, and a new recent-folders list.
  const onFoldersChanged = useCallback(() => {
    api.config().then(setConfig).catch(() => {})
    return refreshEntries()
  }, [refreshEntries])

  useEffect(() => {
    api.config().then(setConfig).catch(() => {})
    refreshEntries().then((list) => {
      if (url.case) return           // embedded or bookmarked: open it directly
      if (list.length === 1) openCase(list[0].id)
      else setStart({ show: true, notice: null })
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // -- metadata --------------------------------------------------------

  useEffect(() => {
    if (!caseKey) return undefined
    let cancelled = false
    setOpening(true)
    api.meta(caseKey).then((m) => {
      if (cancelled) return
      setOpening(false)
      setMeta(m)
      // A case switch keeps the appearance but rebuilds the request: bounds,
      // fields and time steps are all new. The request carries the case's id,
      // so every later call names it unambiguously.
      setRequestState((r) => (r && r.case === (m.caseId ?? m.case) ? r : initialRequest(m)))
    }).catch((e) => {
      if (cancelled) return
      setOpening(false)
      if (e instanceof ApiError && [404, 422, 507].includes(e.status)) {
        // A stale bookmark, a deleted case, or a zip that cannot be unpacked:
        // say so, and offer the others.
        const reason = e.message.startsWith('no case') ? 'not found' : e.message
        setStart({ show: true, notice: `Case “${caseKey}”: ${reason}.` })
        refreshEntries()
      }
      // Anything else is surfaced by the scene fetch, as before.
    })
    return () => { cancelled = true }
  }, [caseKey, refreshEntries])

  // -- the colour table ------------------------------------------------

  // 768 bytes per preset, fetched once and cached hard. Switching a colour map
  // is a texture upload: no geometry request, which is the whole point.
  useEffect(() => {
    let cancelled = false
    const apply = (rgb) => {
      if (cancelled) return
      viewerRef.current?.setLut(rgb)
      setLut(rgb)
    }
    const cached = lutCache.current.get(appearance.preset)
    if (cached) { apply(cached); return undefined }
    api.lut(appearance.preset).then((rgb) => {
      lutCache.current.set(appearance.preset, rgb)
      apply(rgb)
    }).catch(() => {})
    return () => { cancelled = true }
  }, [appearance.preset])

  // -- appearance -> viewer --------------------------------------------
  //
  // Every one of these is a uniform or a GPU flag, so this whole block is
  // instant and provably causes no fetch (tests/check_client.py asserts zero
  // /api/scene requests for each of them).

  // The patch field shows one flat band per patch id over the server's
  // range, which centres each id in its band; the user's range and bands
  // stay untouched for the next real field.
  const patchMode = !!meta?.patchField && request?.field === meta.patchField
    && dataRange?.field === request.field
  const shownRange = patchMode ? dataRange.range : appearance.range
  const shownBands = patchMode
    ? Math.round(dataRange.range[1] - dataRange.range[0]) : appearance.bands

  useEffect(() => {
    viewerRef.current?.setRange(shownRange[0], shownRange[1])
  }, [shownRange])

  useEffect(() => { viewerRef.current?.setBands(shownBands) }, [shownBands])

  useEffect(() => {
    for (const [part, style] of Object.entries(appearance.styles)) {
      viewerRef.current?.setStyle(part, style)
    }
  }, [appearance.styles])

  useEffect(() => {
    for (const [part, on] of Object.entries(appearance.visible)) {
      viewerRef.current?.setVisible(part, on)
    }
  }, [appearance.visible])

  useEffect(() => { viewerRef.current?.setLighting(appearance.lighting) }, [appearance.lighting])

  useEffect(() => { viewerRef.current?.setComets(appearance.comets) }, [appearance.comets])

  useEffect(() => { viewerRef.current?.setTubes(appearance.tubes) }, [appearance.tubes])

  // Scale the default tube radius to the case the first time its bounds arrive.
  useEffect(() => {
    if (!meta) return
    setAppearanceState((a) => (a.tubes.sized === meta.case
      ? a
      : { ...a, tubes: { ...a.tubes, radius: domain * 0.0015, sized: meta.case } }))
  }, [meta, domain])

  useEffect(() => {
    viewerRef.current?.setTheme(appearance.theme === 'light')
  }, [appearance.theme])

  // -- the scene -------------------------------------------------------

  const onHeader = useCallback((header) => {
    // Auto range tracks the data as field or time changes; manual leaves it be.
    setDataRange({ field: header.field, range: header.range })
    setAppearanceState((a) => (a.autoRange ? { ...a, range: header.range } : a))
  }, [])

  const { busy, error, info } = useScene({
    meta, request: request || {}, appearance, viewerRef, onHeader,
  })

  /* The isosurface's values, re-seeded whenever the field it contours CHANGES
   * IDENTITY -- not when the user edits a value.
   *
   * This is the fix for the isosurface behaving "randomly": the values were
   * seeded exactly once per case, so switching the colour field from U to T
   * left the isovalue at a |U| number, i.e. nowhere near the T range, and the
   * surface came back empty or arbitrary. It contours whatever field is
   * selected, so its values have to follow that field's units.
   *
   * Deps are field IDENTITY only (case, colour field/component, the locked
   * field), so typing a value never triggers a reseed.
   */
  const isoField = request?.contour_field || request?.field
  const isoComponent = request?.contour_field ? 'magnitude' : request?.component
  useEffect(() => {
    if (!request?.case || !isoField) return undefined
    const kept = keepContour.current
    keepContour.current = null
    if (kept === `${request.case}|${isoField}|${isoComponent}`) return undefined
    let cancelled = false
    api.range({ case: request.case, field: isoField, component: isoComponent })
      .then(({ range: [lo, hi] }) => {
        if (cancelled) return
        setRequest({
          contour_min: round(lo),
          contour_max: round(hi),
          contour_value: round(lo + (hi - lo) / 2),
        })
      })
      .catch(() => {})
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [request?.case, isoField, isoComponent])

  /* The colour range, when only `robust` moved.
   *
   * `robust` changes no geometry, so it is deliberately in no part's
   * PART_INPUTS -- which meant it moved no signature, triggered no refetch and
   * silently did nothing. It gets the range from the cheap endpoint instead, so
   * it stays instant rather than re-extracting every visible part to deliver
   * two floats. (A scene fetch still reports the range in its header, which is
   * what keeps auto-range tracking a time step; both come from the same server
   * function, so they agree.)
   */
  useEffect(() => {
    if (!request?.case || !request?.field) return undefined
    let cancelled = false
    api.range({
      case: request.case,
      field: request.field,
      component: request.component,
      robust: request.robust ? 1 : 0,
    }).then(({ range }) => {
      if (cancelled) return
      setDataRange({ field: request.field, range })
      setAppearanceState((a) => (a.autoRange ? { ...a, range } : a))
    }).catch(() => {})
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [request?.case, request?.field, request?.component, request?.robust])

  // -- actions ---------------------------------------------------------

  const setStyle = useCallback((part, patch) => {
    setAppearanceState((a) => ({
      ...a,
      styles: { ...a.styles, [part]: { ...(a.styles[part] || {}), ...patch } },
    }))
  }, [])

  /* The cut-plane drag. This is the interaction the whole architecture is
   * arranged around: `onDrag` moves a Vector3 in the browser (the red frame
   * follows the thumb, no request, no extraction) and `onCommit` fires exactly
   * one refetch of the parts that actually depend on the plane. */
  const plane = {
    onDrag: (coord) => {
      const viewer = viewerRef.current
      if (!viewer || !request) return
      viewer.setOutlineAxis(request.plane_axis)
      viewer.moveOutline(coord)
      viewer.showOutline(true)
    },
    onCommit: (coord) => {
      if (!request) return
      viewerRef.current?.showOutline(false)
      setRequest({ plane: { ...request.plane, [request.plane_axis]: coord } })
    },
  }

  // Re-point the outline whenever the normal changes, so the first drag after an
  // axis switch shows a frame in the right plane.
  useEffect(() => {
    if (request?.plane_axis) viewerRef.current?.setOutlineAxis(request.plane_axis)
  }, [request?.plane_axis])

  const setComets = useCallback((patch) => {
    setAppearanceState((a) => ({ ...a, comets: { ...a.comets, ...patch } }))
  }, [])

  const setTubes = useCallback((patch) => {
    setAppearanceState((a) => ({ ...a, tubes: { ...a.tubes, ...patch } }))
  }, [])

  const onView = useCallback((direction) => viewerRef.current?.setView(direction), [])
  const onReset = useCallback(() => {
    if (info) viewerRef.current?.frameAll(info.header.bounds)
  }, [info])
  const onPick = useCallback((x, y) => viewerRef.current?.pickCentre(x, y), [])
  useShortcuts({ onView, onReset, onPick })

  const onRescale = useCallback(async () => {
    if (!request?.field) return
    // Swallowed on purpose: a failed range lookup should leave the current
    // range alone, not reject unhandled out of a click handler.
    const answer = await api.range({
      case: request.case,
      field: request.field,
      component: request.component,
      robust: request.robust ? 1 : 0,
    }).catch(() => null)
    if (!answer) return
    const { range } = answer
    setAppearance({ range })
    // The Trame app's _rescale also re-seeded the isosurface from the new
    // range. Kept -- except when the isosurface is locked to a field of its
    // own, where moving its values would defeat the point of locking.
    if (!request.contour_field) {
      const [lo, hi] = range
      setRequest({
        contour_min: round(lo),
        contour_max: round(hi),
        contour_value: round(lo + (hi - lo) / 2),
      })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [request?.case, request?.field, request?.component, request?.robust,
      request?.contour_field, setAppearance, setRequest])

  const onScreenshot = useCallback(() => {
    const data = viewerRef.current?.screenshot()
    if (!data) return
    const link = document.createElement('a')
    link.href = data
    link.download = `foamviz-${meta?.case || 'scene'}-t${info?.header.time ?? 0}.png`
    link.click()
  }, [request?.case, info])

  // -- saved views -------------------------------------------------------

  const caseId = request?.case
  useEffect(() => {
    if (!caseId) return undefined
    let cancelled = false
    setViewsNotice(null)
    localStore.load(caseId).then((doc) => { if (!cancelled) setViews(doc) })
    return () => { cancelled = true }
  }, [caseId])

  // Every edit saves the whole document (C2).
  const editViews = useCallback((doc) => {
    setViews(doc)
    localStore.save(caseId, doc).catch((e) => setViewsNotice({ color: 'red', text: e.message }))
  }, [caseId])

  const onLoadCamera = useCallback((slot) => {
    const camera = views.cameras[slot]
    if (camera) viewerRef.current?.set_camera(camera)
  }, [views])

  const onStoreCamera = useCallback((slot) => {
    const camera = viewerRef.current?.camera_state()
    if (camera) editViews({ ...views, cameras: { ...views.cameras, [slot]: camera } })
  }, [views, editViews])

  const onSaveScene = useCallback((name, withCamera) => {
    const camera = withCamera ? viewerRef.current?.camera_state() : null
    const scene = sceneFrom(name, request, appearance, camera)
    const at = views.scenes.findIndex((s) => s.name === name)
    const scenes = at < 0 ? [...views.scenes, scene] : views.scenes.map((s, i) => (i === at ? scene : s))
    editViews({ ...views, scenes })
  }, [request, appearance, views, editViews])

  const onLoadScene = useCallback((name) => {
    const scene = views.scenes.find((s) => s.name === name)
    if (!scene || !meta) return
    const next = applyScene(scene, meta, { request, appearance })
    const r = next.request
    keepContour.current = `${r.case}|${r.contour_field || r.field}|${r.contour_field ? 'magnitude' : r.component}`
    setRequestState(next.request)
    setAppearanceState(next.appearance)
    if (scene.camera) viewerRef.current?.set_camera(scene.camera)
    setViewsNotice(next.skipped.length
      ? { color: 'orange', text: `Not in this case, defaults used: ${next.skipped.join('; ')}.` }
      : null)
  }, [views, meta, request, appearance])

  const onRenameScene = useCallback((from, to) => {
    editViews({ ...views, scenes: views.scenes.map((s) => (s.name === from ? { ...s, name: to } : s)) })
  }, [views, editViews])

  const onDeleteScene = useCallback((name) => {
    editViews({ ...views, scenes: views.scenes.filter((s) => s.name !== name) })
  }, [views, editViews])

  const onExportViews = useCallback(() => {
    const blob = new Blob([JSON.stringify(views, null, 2)], { type: 'application/json' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `${meta?.case || 'case'}-views.json`
    link.click()
    setTimeout(() => URL.revokeObjectURL(link.href), 0)
  }, [views, meta])

  const onImportViews = useCallback(async (file) => {
    try {
      const incoming = readViews(JSON.parse(await file.text()))
      const { doc, scenes, slots } = importViews(views, incoming)
      editViews(doc)
      const cams = slots.length ? `, camera${slots.length > 1 ? 's' : ''} ${slots.join(', ')}` : ''
      setViewsNotice({ color: 'blue', text: `Imported ${scenes} scene${scenes === 1 ? '' : 's'}${cams}.` })
    } catch (e) {
      const reason = e instanceof SyntaxError ? 'not a views file' : e.message
      setViewsNotice({ color: 'red', text: `Import failed: ${reason}.` })
    }
  }, [views, editViews])

  const onRefreshTimes = useCallback(async () => {
    const { times } = await api.times(request.case)
    setMeta((m) => ({ ...m, times }))
    setRequest({ time_index: Math.max(times.length - 1, 0) })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [request?.case])

  // One stable tree, always. `request` is null only until /api/meta answers;
  // substituting a placeholder is what keeps `.stage` -- and therefore the
  // Viewer's container and its WebGL context -- mounted from the first commit.
  const req = request || EMPTY_REQUEST

  const legendTitle = [
    info?.header.field ?? req.field,
    meta && meta.fields[req.field] === 3 ? `(${req.component})` : '',
    info?.header.unit ?? '',
  ].filter(Boolean).join(' ')

  return (
    <div className="app" data-theme={appearance.theme}>
      <TopBar
        meta={meta}
        request={req}
        setRequest={setRequest}
        appearance={appearance}
        setAppearance={setAppearance}
        onRescale={onRescale}
        onScreenshot={onScreenshot}
      />
      <div className="body">
        <div className="stage" ref={stageRef}>
          <Hud info={info} stats={stats} />
          <Legend
            lut={lut}
            range={shownRange}
            bands={shownBands}
            ids={patchMode}
            title={legendTitle}
          />
          <BottomBar
            meta={meta}
            request={req}
            setRequest={setRequest}
            onView={onView}
            onRefreshTimes={onRefreshTimes}
            cameras={views.cameras}
            onLoadCamera={onLoadCamera}
            onStoreCamera={onStoreCamera}
          />
          <Busy
            show={!start.show && (opening || busy || !request)}
            label={opening ? 'Opening case…' : 'Extracting…'}
            error={start.show ? null : error}
          />
        </div>
        <SidePane
          meta={meta}
          entries={entries}
          onOpenCase={openCase}
          onShowCases={showCases}
          request={req}
          setRequest={setRequest}
          appearance={appearance}
          setAppearance={setAppearance}
          setStyle={setStyle}
          plane={plane}
          comets={appearance.comets}
          setComets={setComets}
          canAnimate={canAnimate}
          tubes={appearance.tubes}
          setTubes={setTubes}
          domain={domain}
          views={views}
          viewsNotice={viewsNotice}
          onDismissNotice={() => setViewsNotice(null)}
          onSaveScene={onSaveScene}
          onLoadScene={onLoadScene}
          onRenameScene={onRenameScene}
          onDeleteScene={onDeleteScene}
          onExportViews={onExportViews}
          onImportViews={onImportViews}
        />
      </div>
      {start.show && (
        <StartScreen
          entries={entries}
          config={config}
          notice={start.notice}
          loading={entriesLoading}
          onOpen={openCase}
          onRefresh={refreshEntries}
          onFoldersChanged={onFoldersChanged}
          onCacheCleared={refreshConfig}
          onClose={meta && !start.notice ? () => setStart({ show: false, notice: null }) : null}
        />
      )}
    </div>
  )
}

const round = (v) => Number(v.toPrecision(6))

/* Stands in for `request` between mount and the first /api/meta response. Only
 * ever read, never sent: useScene refuses to fetch without a field. */
const EMPTY_REQUEST = {
  case: '', field: '', component: 'magnitude', plane_axis: 'z',
  plane: { x: 0, y: 0, z: 0 }, patches: [], time_index: 0,
}
