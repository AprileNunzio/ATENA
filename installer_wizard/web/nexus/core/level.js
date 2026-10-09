import { api } from "./http.js";
import { store } from "./store.js";

export const LEVELS = [
  { id: "explorer", label: "Esploratore", hint: "Poche scelte chiare, ti guida Atena" },
  { id: "pilot", label: "Pilota", hint: "Zone, interruttori e modelli pronti" },
  { id: "architect", label: "Architetto", hint: "Tutto: file, priorità, JSON e log" },
];
const RANK = { explorer: 0, pilot: 1, architect: 2 };
const CACHE_KEY = "nexus.level";

export const rank = (level) => RANK[level] ?? 1;
export const allows = (minimum, level = store.get().level) => rank(level) >= rank(minimum);

export function cachedLevel() {
  try {
    const value = localStorage.getItem(CACHE_KEY);
    return value in RANK ? value : null;
  } catch {
    return null;
  }
}

export function applyLevel(level) {
  document.body.dataset.level = level;
  try { localStorage.setItem(CACHE_KEY, level); } catch {}
}

export async function chooseLevel(level) {
  if (!(level in RANK)) return;
  const previous = store.get().level;
  applyLevel(level);
  store.set({ level });
  try {
    await api("/api/nexus/preferences", { method: "PUT", body: { level } });
  } catch (err) {
    applyLevel(previous);
    store.set({ level: previous });
    throw err;
  }
}
