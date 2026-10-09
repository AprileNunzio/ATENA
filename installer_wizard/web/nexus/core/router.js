import { store } from "./store.js";

const ROUTE = /^[a-z][a-z0-9-]{0,30}$/;
const routes = new Map();
let fallback = "home";

export function define(id, view) {
  routes.set(id, view);
}

export function setFallback(id) {
  fallback = id;
}

export function current() {
  const [id, ...rest] = location.hash.replace(/^#\/?/, "").split("/");
  return { id: ROUTE.test(id) && routes.has(id) ? id : fallback, param: rest.join("/") };
}

export function go(id, param = "") {
  const target = `#/${id}${param ? `/${param}` : ""}`;
  if (location.hash === target) window.dispatchEvent(new HashChangeEvent("hashchange"));
  else location.hash = target;
}

export function view(id) {
  return routes.get(id);
}

export function start(render) {
  const run = () => {
    const route = current();
    store.set({ route: route.id });
    render(route);
  };
  window.addEventListener("hashchange", run);
  run();
  return () => window.removeEventListener("hashchange", run);
}
