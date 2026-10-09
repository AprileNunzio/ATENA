import { h } from "../../core/dom.js";
import { sparkline } from "../../components/charts.js";
import { SERIES } from "./series.js";

const GB = 1024 ** 3;
const gb = (bytes) => (bytes / GB).toLocaleString("it-IT", { maximumFractionDigits: 1 });
const COMPONENT_PILL = { ok: ["ok", "attivo"], warn: ["warn", "a metà"], down: ["bad", "fermo"] };
const EVENT_SEVERITY = { ERROR: "bad", WARN: "warn", INFO: "info" };

function uptime(seconds) {
  const d = Math.floor(seconds / 86400), hrs = Math.floor((seconds % 86400) / 3600), min = Math.floor((seconds % 3600) / 60);
  return d ? `${d} g ${hrs} h` : hrs ? `${hrs} h ${min} min` : `${min} min`;
}

function tile(label, value, unit, note, series, max = 100) {
  return h("div", { class: "panel stat" },
    h("p", { class: "ptitle" }, label),
    h("div", { class: "stat-v" }, value ?? "—", value != null ? h("small", {}, unit) : null),
    h("div", { class: "stat-note" }, note),
    sparkline(series.values, { max }));
}

export function statTiles(sys) {
  if (!sys) return [1, 2, 3, 4].map(() => h("div", { class: "panel stat skeleton-tile" }, h("div", { class: "skeleton" })));
  return [
    tile("Processore", Math.round(sys.cpu_percent), "%", `${sys.cpu_count} core · carico ${sys.load?.[0] ?? "—"}`, SERIES.cpu),
    tile("Memoria", Math.round(sys.mem_percent), "%", `${gb(sys.mem_used)} di ${gb(sys.mem_total)} GB`, SERIES.mem),
    tile("Disco", Math.round(sys.disk_percent), "%", `${gb(sys.disk_total - sys.disk_used)} GB liberi`, SERIES.disk),
    tile("Temperatura", sys.temperature != null ? Math.round(sys.temperature) : null, "°C",
      `${sys.hostname} · acceso da ${uptime(sys.uptime)}`, SERIES.temp, 100),
  ];
}

export function todoPanel(todos) {
  const items = todos.length
    ? todos.map((t) => h("li", {}, h("a", { class: "todo", href: t.target ? `/#${t.target}` : `#/${t.zone}` },
      h("span", { class: `sev ${t.severity === "info" ? "" : t.severity}` }), h("span", { class: "todo-text" }, t.text),
      h("span", { class: "todo-go", "aria-hidden": "true" }, "→"))))
    : [h("li", { class: "todo-empty" }, h("span", { class: "sev ok" }), "Niente da fare: va tutto bene.")];
  return [h("p", { class: "ptitle" }, "Cose da fare"), h("ul", { class: "todos" }, items)];
}

export function activityPanel(events) {
  const recent = (events || []).slice(-7).reverse();
  return [h("p", { class: "ptitle" }, "Attività recenti"),
    recent.length
      ? h("ul", { class: "feed" }, recent.map((e) => h("li", {},
        h("time", { datetime: e.ts }, new Date(e.ts).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" })),
        h("span", { class: `sev ${EVENT_SEVERITY[e.level] === "info" ? "" : EVENT_SEVERITY[e.level] || ""}` }),
        h("span", { class: "feed-msg" }, e.msg))))
      : h("p", { class: "dim" }, "Ancora nessuna attività registrata.")];
}

export function componentsPanel(components) {
  return [h("p", { class: "ptitle" }, "Componenti"),
    h("div", { class: "tbl-wrap" }, h("table", {},
      h("thead", {}, h("tr", {}, h("th", {}, "Componente"), h("th", {}, "Stato"), h("th", {}, "Dettaglio"))),
      h("tbody", {}, components.map((c) => {
        const [tone, label] = c.on_demand ? ["", "su richiesta"] : COMPONENT_PILL[c.status] || ["", c.status || "—"];
        return h("tr", {}, h("td", {}, c.label), h("td", {}, h("span", { class: `pill ${tone}` }, label)),
          h("td", { class: "mono dim cell-detail" }, c.detail || ""));
      }))))];
}
