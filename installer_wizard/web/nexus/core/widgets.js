import { api } from "./http.js";
import { toast } from "./toast.js";

const MESSAGES = {
  live: (name) => `${name}: aperto sul display con i dati dal vivo`,
  last: (name) => `${name}: riaperto sul display con gli ultimi dati`,
  preview: (name) => `${name}: anteprima sul display. Chiedilo ad Atena per i dati veri`,
};
let cache = null, pending = null;

export async function widgets() {
  if (cache) return cache;
  if (!pending) {
    pending = api("/api/widgets").then((data) => {
      cache = (data.widgets || []).filter((w) => w.enabled && w.id !== "alarm");
      return cache;
    }).finally(() => { pending = null; });
  }
  return pending;
}

export const cachedWidgets = () => cache || [];

export async function recall(widget) {
  const result = await api(`/api/widgets/${encodeURIComponent(widget.id)}/recall`, { method: "POST" });
  toast((MESSAGES[result.origin] || MESSAGES.preview)(widget.name));
  return result.origin;
}
