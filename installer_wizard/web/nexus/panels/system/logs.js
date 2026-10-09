import { api, button, h, live, mount, row, section, select, spacer, toggle } from "../kit.js";

const SOURCES = [
  ["install", "Installazione e step"],
  ["supervisor", "Supervisore"],
  ["core", "Atena Core"],
  ["ollama", "Motore neurale"],
  ["kiosk", "Display kiosk"],
  ["rollback", "Rollback"],
];

export default function logs(root) {
  let source = "install", auto = true;
  const text = h("pre", { class: "np-log np-log-tall", tabindex: "0", "aria-live": "off" }, "…");
  const load = async () => {
    try {
      const d = await api(`/api/logs/${source}?lines=400`);
      const atBottom = text.scrollTop + text.clientHeight >= text.scrollHeight - 30;
      text.textContent = d.text || "(vuoto)";
      if (atBottom) text.scrollTop = text.scrollHeight;
    } catch (err) { text.textContent = err.message; }
  };
  mount(root, section(null,
    row(select(SOURCES, source, (v) => { source = v; load(); }, "Registro"),
      button("Aggiorna", load, { kind: "ghost" }), spacer(),
      toggle("Aggiorna da solo", auto, (v) => { auto = v; })),
    text));
  live(root, () => (auto ? load() : null), 4000);
}
