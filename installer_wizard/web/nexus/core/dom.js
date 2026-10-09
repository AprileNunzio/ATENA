const SVG_NS = "http://www.w3.org/2000/svg";

function assign(el, props) {
  for (const [key, value] of Object.entries(props || {})) {
    if (value == null || value === false) continue;
    if (key === "class") el.setAttribute("class", value);
    else if (key === "dataset") Object.assign(el.dataset, value);
    else if (key === "style") Object.assign(el.style, value);
    else if (key.startsWith("on") && typeof value === "function") el.addEventListener(key.slice(2), value);
    else el.setAttribute(key, value === true ? "" : String(value));
  }
}

function append(el, kids) {
  for (const kid of kids.flat(Infinity)) {
    if (kid == null || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
}

export function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  assign(el, props);
  append(el, kids);
  return el;
}

export function svg(tag, props, ...kids) {
  const el = document.createElementNS(SVG_NS, tag);
  assign(el, props);
  append(el, kids);
  return el;
}

export function mount(target, ...kids) {
  target.replaceChildren();
  append(target, kids);
  return target;
}

export const $ = (query, root = document) => root.querySelector(query);
export const $$ = (query, root = document) => [...root.querySelectorAll(query)];
export const reducedMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
