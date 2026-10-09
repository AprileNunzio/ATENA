import { actions, api, bar, dots, button, fmt, grid, h, mount, note, onSnapshot, pill, section, table, toast } from "../kit.js";

const RESTARTABLE = new Set(["core", "qdrant", "ollama", "docker", "kiosk"]);
const COMPONENT = { ok: ["operativo", "ok"], warn: ["attenzione", "warn"], down: ["guasto", "bad"] };
const PHASE = { READY: "ok", DEGRADED: "warn", ERROR: "bad" };

const act = (name, body) => api(`/api/actions/${name}`, { method: "POST", body }).then((r) => toast(r.message || (r.ok === false ? "Operazione non riuscita" : "Operazione avviata"), { error: r.ok === false }));

function stat(label, value, sub, percent) {
  return h("div", { class: "np-card" }, h("p", { class: "ptitle" }, label), h("div", { class: "np-big" }, value), percent == null ? null : bar(percent, percent > 90 ? "bad" : percent > 75 ? "warn" : ""), h("div", { class: "np-sub" }, sub));
}

export default function overview(root) {
  const stats = h("div", { class: "np-cards" });
  const current = h("div", { class: "np-sec" });
  const components = h("div");
  mount(root,
    stats,
    grid(
      section("Componenti", components),
      section("Azioni rapide",
        actions(
          button("Verifica e ripara tutto", () => act("repair"), { kind: "primary" }),
          button("Controlla aggiornamenti", () => act("update-check")),
          button("Riavvia supervisore", () => act("restart-supervisor"), { confirm: { title: "Riavviare il supervisore?", text: "L'interfaccia si ricollegherà automaticamente.", action: "Riavvia" } }),
          button("Riavvia sistema", () => act("reboot"), { kind: "danger", confirm: { title: "Riavviare il sistema?", text: "Atena tornerà disponibile tra qualche minuto.", action: "Riavvia", danger: true } })),
        h("p", { class: "ptitle" }, "Stato corrente"), current)));

  onSnapshot(root, (s) => {
    const sys = s.system || {};
    if (sys.mem_total) mount(stats,
      stat("Processore", `${fmt.num(sys.cpu_percent)}%`, `${sys.cpu_count} core · carico ${(sys.load || []).join(" / ")}${sys.temperature ? ` · ${sys.temperature} °C` : ""}`, sys.cpu_percent),
      stat("Memoria", `${fmt.num(sys.mem_percent)}%`, `${fmt.bytes(sys.mem_used)} di ${fmt.bytes(sys.mem_total)}`, sys.mem_percent),
      stat("Disco", `${fmt.num(sys.disk_percent)}%`, `${fmt.bytes(sys.disk_used)} di ${fmt.bytes(sys.disk_total)}`, sys.disk_percent),
      stat("Sistema", fmt.duration(sys.uptime), `${sys.hostname} · ${sys.ip} · ↓${fmt.rate(sys.net_rx_rate)} ↑${fmt.rate(sys.net_tx_rate)}`));
    const b = s.brains || {};
    mount(current,
      h("div", { class: "np-row" }, pill(s.phase_label || s.phase, PHASE[s.phase] || "info"), h("span", { class: "dim small" }, s.phase === "READY" ? `v${s.supervisor_version}` : `${Math.floor(s.progress || 0)}%`)),
      h("div", {}, s.message || ""),
      s.detail ? h("div", { class: "mono dim small" }, s.detail) : null,
      s.last_error ? h("div", { class: "np-err" }, s.last_error) : null,
      bar(s.progress || 0),
      note(dots(`Avvio n. ${s.boot_count}`, `fase attiva da ${fmt.duration(Date.now() / 1000 - s.phase_since)}`, h("span", {}, "conversazione ", h("span", { class: "mono" }, b.chat || "—")), h("span", {}, "ragionamento ", h("span", { class: "mono" }, b.deep || s.llm_model || "—")), b.last ? h("span", {}, "ultima risposta: ", h("span", { class: "mono" }, b.last)) : null)));
    const rows = Object.entries(s.components || {}).map(([key, c]) => {
      const [label, tone] = c.on_demand ? ["su richiesta", ""] : COMPONENT[c.status] || [c.status, ""];
      return [h("div", {}, c.label, h("div", { class: "mono dim small" }, c.detail || "")), pill(label, tone),
        RESTARTABLE.has(key) ? h("div", { class: "cell-actions" }, button("Riavvia", () => act("restart-component", { component: key }), { kind: "ghost sm", confirm: { title: `Riavviare ${c.label}?`, action: "Riavvia" } })) : ""];
    });
    mount(components, table(["Componente", "Stato", ""], rows, "Diagnosi disponibile quando il sistema è operativo."));
  });
}
