export class HttpError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

const TIMEOUT_MS = 20000;
const listeners = new Set();

export const onUnauthorized = (fn) => listeners.add(fn);

async function detail(response) {
  try {
    const data = await response.json();
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail)) return data.detail.map((d) => d.msg).join("; ");
  } catch {}
  return `Errore ${response.status}`;
}

export async function api(path, { method = "GET", body, timeout = TIMEOUT_MS } = {}) {
  if (!path.startsWith("/api/")) throw new HttpError(0, "Percorso non consentito");
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  const headers = { Accept: "application/json", "X-Atena-Request": "1" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  let response;
  try {
    response = await fetch(path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "same-origin",
      cache: "no-store",
      redirect: "error",
      signal: controller.signal,
    });
  } catch (err) {
    throw new HttpError(0, err.name === "AbortError" ? "Atena non risponde: riprova tra poco" : "Connessione con Atena assente");
  } finally {
    clearTimeout(timer);
  }
  if (response.status === 401 && path !== "/api/auth/login") listeners.forEach((fn) => fn());
  if (!response.ok) throw new HttpError(response.status, await detail(response));
  return response.status === 204 ? null : response.json();
}

export function stream(path, onMessage, onLink) {
  let source = null, retry = 1000, stopped = false;
  const open = () => {
    if (stopped) return;
    source = new EventSource(path, { withCredentials: true });
    source.onopen = () => { retry = 1000; onLink?.(true); };
    source.onmessage = (event) => {
      try { onMessage(JSON.parse(event.data)); } catch (err) { console.warn("Messaggio non valido dal flusso", err); }
    };
    source.onerror = () => {
      source.close();
      onLink?.(false);
      setTimeout(open, retry);
      retry = Math.min(retry * 2, 15000);
    };
  };
  open();
  return () => { stopped = true; source?.close(); };
}
