// The views document and the local store under Node (openspec scenes-and-cameras
// tasks 1.1, 1.2). Run by tests/test_views_document.py; exits non-zero on the
// first failed assertion.
import assert from 'node:assert/strict'
import {
  applyScene, emptyViews, importViews, readViews, sceneFrom,
} from '../web/src/views/document.js'
import { initialAppearance, initialRequest } from '../web/src/scene/state.js'

const meta = {
  caseId: 'abc', times: [0, 10], colorField: 'T', vectorField: 'U',
  fields: { T: 1, U: 3, p: 1 }, vectorFields: ['U'], patches: ['floor', 'walls'],
  centre: [1, 2, 3],
}
const current = {
  request: { ...initialRequest(meta), time_index: 0 },
  appearance: {
    ...initialAppearance('dark'), activeTool: 'glyph',
    tubes: { on: false, radius: 0.01, sides: 8, sized: 'abc' },
  },
}

// sceneFrom leaves out what the app owns.
const saved = {
  ...current.request, case: 'other', time_index: 1, field: 'p', plane: { x: 1, y: 2, z: 1.1 },
}
const look = {
  ...current.appearance, autoRange: false, range: [290, 310], theme: 'light',
  tubes: { on: true, radius: 0.05, sides: 8, sized: 'x' }, activeTool: 'cutplane',
}
const scene = sceneFrom('Slice', saved, look, { position: [1, 2, 3], target: [0, 0, 0], up: [0, 0, 1], fov: 45 })
for (const k of ['case', 'time_index']) assert.ok(!(k in scene.request), `request keeps ${k}`)
for (const k of ['theme', 'activeTool']) assert.ok(!(k in scene.appearance), `appearance keeps ${k}`)
assert.ok(!('sized' in scene.appearance.tubes), 'tubes.sized saved')

// Applied: the scene's settings, the app's own keys from the current state.
let out = applyScene(scene, meta, current)
assert.equal(out.request.field, 'p')
assert.equal(out.request.plane.z, 1.1)
assert.equal(out.request.case, 'abc')
assert.equal(out.request.time_index, 0)
assert.equal(out.appearance.theme, 'dark')
assert.equal(out.appearance.activeTool, 'glyph')
assert.equal(out.appearance.tubes.sized, 'abc')
assert.equal(out.appearance.tubes.radius, 0.05)
assert.deepEqual(out.appearance.range, [290, 310])
assert.equal(out.appearance.autoRange, false)
assert.deepEqual(out.skipped, [])

// An empty contour_field is valid and not skipped.
assert.equal(out.request.contour_field, '')

// Fallbacks for what the case lacks; world units stay as stored (D10).
const foreign = sceneFrom('Foreign', {
  ...saved, field: 'CO2', vector_field: 'V', contour_field: 'k', patches: ['floor', 'inlet'],
  plane: { x: 99, y: 99, z: 99 },
}, look)
out = applyScene(foreign, meta, current)
assert.equal(out.request.field, 'T')
assert.equal(out.request.vector_field, 'U')
assert.equal(out.request.contour_field, '')
assert.deepEqual(out.request.patches, ['floor'])
assert.equal(out.request.plane.x, 99)
assert.deepEqual(out.skipped, ['field CO2', 'vector field V', 'isosurface field k', 'patch inlet'])

// An older document: a missing key takes its default, an extra one is dropped.
const old = { name: 'Old', request: { field: 'p', retired: 1 }, appearance: { styles: { slice: { opacity: 0.5 } } }, camera: null }
out = applyScene(old, meta, current)
assert.equal(out.request.field, 'p')
assert.ok(!('retired' in out.request))
assert.equal(out.request.glyph_count, initialRequest(meta).glyph_count)
assert.equal(out.appearance.styles.slice.opacity, 0.5)
assert.equal(out.appearance.styles.slice.colored, true)

// readViews: round trip, refusals.
const doc = emptyViews()
doc.scenes.push(scene)
doc.cameras[2] = scene.camera
const back = readViews(JSON.parse(JSON.stringify(doc)))
assert.deepEqual(back, doc)
assert.throws(() => readViews({ format: 'equa-cfd-views', version: 2 }), /newer viewer/)
assert.throws(() => readViews({ format: 'something', version: 1 }), /not a views file/)

// importViews: names suffixed, only filled slots overwritten.
const mine = emptyViews()
mine.scenes.push({ ...scene, name: 'Slice' })
mine.cameras[1] = { position: [9, 9, 9], target: [0, 0, 0], up: [0, 0, 1], fov: 45 }
const merged = importViews(mine, back)
assert.deepEqual(merged.doc.scenes.map((s) => s.name), ['Slice', 'Slice (2)'])
assert.deepEqual(merged.doc.cameras[1].position, [9, 9, 9])
assert.deepEqual(merged.doc.cameras[2].position, [1, 2, 3])
assert.deepEqual(merged.slots, ['2'])

// The local store: a throwing storage loads empty and rejects a save.
globalThis.window = {
  localStorage: {
    getItem() { throw new Error('denied') },
    setItem() { const e = new Error('full'); e.name = 'QuotaExceededError'; throw e },
  },
}
const { localStore } = await import('../web/src/views/localStore.js')
assert.deepEqual(await localStore.load('abc'), emptyViews())
await assert.rejects(localStore.save('abc', doc), /Views not saved/)

// And a working one round-trips.
const box = new Map()
globalThis.window.localStorage = {
  getItem: (k) => box.get(k) ?? null,
  setItem: (k, v) => box.set(k, v),
}
await localStore.save('abc', doc)
assert.ok(box.has('equa-cfd-viewer:views:abc'))
assert.deepEqual(await localStore.load('abc'), doc)
assert.deepEqual(await localStore.load('other'), emptyViews())

console.log('views document: ok')
