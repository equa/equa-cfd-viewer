import { emptyViews, readViews } from './document.js'

/*
 * The views store on the browser's localStorage (saved-views-train C2;
 * scenes-and-cameras A3). Private windows, blocked site data and a full quota
 * all throw, so every access is guarded: a load falls back to an empty
 * document, a save rejects with a message for the notice.
 */

const key = (caseId) => `equa-cfd-viewer:views:${caseId}`

export const localStore = {
  async load(caseId) {
    try {
      const raw = window.localStorage.getItem(key(caseId))
      return raw ? readViews(JSON.parse(raw)) : emptyViews()
    } catch {
      return emptyViews()
    }
  },

  async save(caseId, doc) {
    try {
      window.localStorage.setItem(key(caseId), JSON.stringify(doc))
    } catch (e) {
      throw new Error(`Views not saved: browser storage refused (${e.name || e.message}).`)
    }
  },
}
