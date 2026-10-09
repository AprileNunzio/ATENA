import { api } from "./http.js";
import { store } from "./store.js";

const REFRESH_MS = 30000;
const listeners = new Set();
let data = null, pending = null, timer = 0, lastRev = null;

export const summary = () => data;

export function onSummary(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export async function refresh() {
  if (pending) return pending;
  pending = api("/api/nexus/summary")
    .then((value) => { data = value; listeners.forEach((fn) => fn(value)); return value; })
    .finally(() => { pending = null; });
  return pending;
}

export function startSummary() {
  clearInterval(timer);
  timer = setInterval(() => refresh().catch((err) => console.warn("Riepilogo non aggiornato", err)), REFRESH_MS);
  store.subscribe((state, changed) => {
    if (!changed.includes("snapshot") || !state.snapshot) return;
    const rev = `${state.snapshot.features_rev}|${state.snapshot.phase}`;
    if (rev !== lastRev) { lastRev = rev; refresh().catch(() => {}); }
  });
  return refresh();
}

export const toolsIn = (zoneId) => (data?.tools || []).filter((t) => t.zone === zoneId);
