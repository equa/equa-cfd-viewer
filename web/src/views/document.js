import { initialAppearance, initialRequest } from '../scene/state.js'

/*
 * The views document: saved scenes and the four camera slots of one case. It is
 * both what a store keeps and the export file, so car B can store it unchanged
 * (openspec saved-views-train C1; scenes-and-cameras A1, A2).
 *
 * Pure functions, no React: tests/test_views_document.py runs them under Node.
 */

export const FORMAT = 'equa-cfd-views'
export const VERSION = 1
export const SLOTS = ['1', '2', '3', '4']

export function emptyViews() {
  return { format: FORMAT, version: VERSION, cameras: { 1: null, 2: null, 3: null, 4: null }, scenes: [] }
}

const clone = (v) => JSON.parse(JSON.stringify(v))

// Set by the app, not the user: never saved, never taken from a scene (A2).
const REQUEST_OWN = ['case', 'time_index']
const APPEARANCE_OWN = ['theme', 'activeTool']

export function sceneFrom(name, request, appearance, camera = null) {
  const req = clone(request)
  for (const k of REQUEST_OWN) delete req[k]
  const look = clone(appearance)
  for (const k of APPEARANCE_OWN) delete look[k]
  if (look.tubes) delete look.tubes.sized
  return { name, request: req, appearance: look, camera: camera ? clone(camera) : null }
}

const isObject = (v) => v !== null && typeof v === 'object' && !Array.isArray(v)

/* `saved` over `base`, taking only keys `base` has and only values of the same
 * kind, so an older document fills in and a stale key is dropped (AR2). */
function merge(base, saved) {
  if (!isObject(saved)) return base
  const out = { ...base }
  for (const [k, v] of Object.entries(base)) {
    if (!(k in saved)) continue
    const s = saved[k]
    if (isObject(v)) out[k] = merge(v, s)
    else if (Array.isArray(v) ? Array.isArray(s) : typeof s === typeof v) out[k] = clone(s)
  }
  return out
}

/* The state a scene asks for on this case. `current` is `{request, appearance}`;
 * `skipped` names each setting the case lacks (D8). World-unit settings load as
 * stored (D10). */
export function applyScene(scene, meta, current) {
  const request = merge(initialRequest(meta), scene.request)
  request.case = current.request.case
  request.time_index = current.request.time_index
  const defaults = initialRequest(meta)
  const skipped = []
  if (!(request.field in meta.fields)) {
    skipped.push(`field ${request.field}`)
    request.field = defaults.field
    request.component = defaults.component
  }
  if (!(meta.vectorFields || []).includes(request.vector_field)) {
    skipped.push(`vector field ${request.vector_field}`)
    request.vector_field = defaults.vector_field
  }
  // '' means "follow the colour field": valid, never skipped.
  if (request.contour_field && !(request.contour_field in meta.fields)) {
    skipped.push(`isosurface field ${request.contour_field}`)
    request.contour_field = ''
  }
  const missing = request.patches.filter((p) => !meta.patches.includes(p))
  if (missing.length) {
    skipped.push(`patch${missing.length > 1 ? 'es' : ''} ${missing.join(', ')}`)
    request.patches = request.patches.filter((p) => meta.patches.includes(p))
  }

  const appearance = merge(initialAppearance(current.appearance.theme), scene.appearance)
  appearance.theme = current.appearance.theme
  if ('activeTool' in current.appearance) appearance.activeTool = current.appearance.activeTool
  if (current.appearance.tubes && 'sized' in current.appearance.tubes) {
    appearance.tubes.sized = current.appearance.tubes.sized
  }
  return { request, appearance, skipped }
}

const isVec3 = (v) => Array.isArray(v) && v.length === 3 && v.every(Number.isFinite)

function readCamera(c) {
  if (!isObject(c) || !isVec3(c.position) || !isVec3(c.target) || !isVec3(c.up)) return null
  return {
    position: [...c.position], target: [...c.target], up: [...c.up],
    fov: Number.isFinite(c.fov) ? c.fov : 45,
  }
}

/* A document from parsed JSON: validated and upgraded, or an Error with a
 * message fit for the user. */
export function readViews(data) {
  if (!isObject(data) || data.format !== FORMAT) throw new Error('not a views file')
  if (!Number.isInteger(data.version) || data.version > VERSION) {
    throw new Error(`views file version ${data.version} needs a newer viewer`)
  }
  const doc = emptyViews()
  for (const slot of SLOTS) doc.cameras[slot] = readCamera(data.cameras?.[slot])
  for (const s of Array.isArray(data.scenes) ? data.scenes : []) {
    if (!isObject(s) || typeof s.name !== 'string' || !s.name.trim()) continue
    doc.scenes.push({
      name: s.name,
      request: isObject(s.request) ? clone(s.request) : {},
      appearance: isObject(s.appearance) ? clone(s.appearance) : {},
      camera: readCamera(s.camera),
    })
  }
  return doc
}

export function uniqueName(name, taken) {
  if (!taken.includes(name)) return name
  let n = 2
  while (taken.includes(`${name} (${n})`)) n += 1
  return `${name} (${n})`
}

/* `incoming` added to `doc`: its scenes appended, a clashing name suffixed, and
 * only the slots it fills overwritten (A8). */
export function importViews(doc, incoming) {
  const out = clone(doc)
  const names = out.scenes.map((s) => s.name)
  for (const s of incoming.scenes) {
    const name = uniqueName(s.name, names)
    names.push(name)
    out.scenes.push({ ...clone(s), name })
  }
  const slots = SLOTS.filter((k) => incoming.cameras[k])
  for (const k of slots) out.cameras[k] = clone(incoming.cameras[k])
  return { doc: out, scenes: incoming.scenes.length, slots }
}
