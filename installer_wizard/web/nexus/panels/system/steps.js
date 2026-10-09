import { api, bar, tag, button, filePick, fmt, h, mount, note, onSnapshot, pill, row, section, spacer, table, toast, upload } from "../kit.js";

const STEP = { pending: ["in attesa", ""], checking: ["verifica", "info"], running: ["in corso", "info"], retrying: ["nuovo tentativo", "warn"], done: ["operativo", "ok"], failed: ["errore", "bad"], skipped: ["saltato", ""], background: ["in background dopo l'avvio", "info"], on_demand: ["su richiesta", ""] };
const BG = { queued: ["in coda", ""], running: ["in corso", "info"], done: ["pronta", "ok"], failed: ["riproverà", "bad"], waiting_disk: ["spazio insufficiente", "bad"] };

export default function steps(root) {
  const bgHead = h("div", { class: "np-sec" });
  const bgList = h("div");
  const stepList = h("div");
  const wakeNote = h("span", { class: "dim small" });
  let snapshot = null;

  const background = async (path) => { snapshot = { ...snapshot, background: await api(path, { method: "POST" }) }; paint(snapshot); };

  function paint(s) {
    snapshot = s;
    const bg = s.background;
    if (bg?.items) {
      const tone = bg.finished ? "ok" : bg.paused ? "bad" : "warn";
      mount(bgHead,
        row(pill(bg.finished ? "completate" : bg.paused ? "in pausa" : bg.conversation ? "attende la fine della conversazione" : "in corso", tone),
          h("span", { class: "dim small" }, `${bg.done} di ${bg.total} pronte · ${bg.progress}%`), spacer(),
          bg.finished ? null : button(bg.paused ? "Riprendi" : "Metti in pausa", () => background(`/api/background/${bg.paused ? "resume" : "pause"}`), { kind: "ghost sm" })),
        bar(bg.progress));
      mount(bgList, table(["Componente", "Dimensione", "Stato", "Dettaglio", ""], bg.items.map((i, n) => {
        const [label, t] = BG[i.status] || [i.status, ""];
        return [h("div", {}, i.title, h("div", { class: "dim small" }, i.description)), h("span", { class: "mono" }, `${fmt.num(i.size_gb, 1)} GB`),
          pill(`${label}${i.status === "running" ? ` ${i.progress}%` : ""}`, t), h("span", { class: "dim small" }, i.detail || i.message || ""),
          i.status !== "done" && n > 0 ? h("div", { class: "cell-actions" }, button("Prima", () => background(`/api/background/prioritize?step=${encodeURIComponent(i.id)}`), { kind: "ghost sm" })) : ""];
      })));
    }
    mount(stepList, table(["Step", "Stato", "Tentativi", "Durata", "Dettaglio", ""], (s.catalog || []).map((c) => {
      const r = s.steps?.[c.id] || { status: "pending" };
      const [label, t] = STEP[r.status] || [r.status, ""];
      return [h("div", {}, c.title, h("div", { class: "dim small" }, c.description, c.critical ? null : tag("opzionale"))),
        pill(`${label}${r.status === "running" ? ` ${r.progress}%` : ""}`, t), h("span", { class: "mono" }, String(r.attempts || 0)),
        h("span", { class: "mono" }, r.duration ? fmt.duration(r.duration) : "—"), h("span", { class: r.error ? "np-err" : "dim small" }, r.error || r.message || ""),
        h("div", { class: "cell-actions" }, button("Riesegui", () => api("/api/actions/rerun-step", { method: "POST", body: { step: c.id } }).then((x) => toast(x.message || "Step avviato")),
          { kind: "ghost sm", disabled: s.busy, confirm: { title: `Rieseguire lo step «${c.title}»?`, action: "Riesegui" } }))];
    })));
  }

  mount(root,
    section("Installazioni in background", bgHead, bgList,
      note("Le parti pesanti si installano dopo l'avvio, una alla volta, con priorità bassa, e si fermano mentre parli con Atena. «Prima» sposta un componente in cima alla coda."),
      row(filePick("Carica modello «Ehi, Atena» (.onnx)", ".onnx", async (file) => {
        try {
          await upload("/api/setup/wakeword", file, { accept: /\.onnx$/i, max: 20 * 1024 * 1024 });
          wakeNote.textContent = `Caricato: ${file.name}`;
          toast("Modello «Ehi, Atena» caricato: l'ascolto si riavvia da solo");
        } catch (err) { toast(err.message, { error: true }); }
      }), wakeNote)),
    section("Step di convergenza", stepList,
      note("Ogni step è idempotente: a ogni avvio viene verificato e riparato solo se necessario. «Riesegui» forza la reinstallazione del componente.")));
  onSnapshot(root, paint);
}
