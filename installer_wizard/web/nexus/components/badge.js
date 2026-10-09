import { h } from "../core/dom.js";

const LABELS = { new: "Novità", updated: "Aggiornato" };
const SEEN_KEY = "nexus.seen";

const day = (seconds) => new Date(seconds * 1000).toLocaleDateString("it-IT", { day: "numeric", month: "long" });

export function freshBadge(item) {
  if (!LABELS[item?.badge]) return null;
  const when = item.since ? day(item.since) : "";
  const text = item.badge === "new" ? `Arrivato il ${when}` : `Aggiornato il ${when}`;
  return h("span", { class: `badge ${item.badge}`, title: text }, LABELS[item.badge],
    h("span", { class: "sr-only" }, `: ${text}`));
}

function seenSet() {
  try { return new Set(JSON.parse(localStorage.getItem(SEEN_KEY) || "[]")); } catch { return new Set(); }
}

export function isSeen(key) {
  return seenSet().has(key);
}

export function markSeen(key) {
  const seen = seenSet();
  if (seen.has(key)) return;
  seen.add(key);
  try { localStorage.setItem(SEEN_KEY, JSON.stringify([...seen].slice(-200))); } catch {}
}

export function countBadge(count, label) {
  return count ? h("span", { class: "count-badge", title: label, "aria-label": label }, String(count)) : null;
}
