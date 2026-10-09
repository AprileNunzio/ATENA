import { actions, api, button, fmt, h, kv, mono, mount, note, pill, section, toast } from "../kit.js";

function state(u) {
  if (u.available) return pill("aggiornamento disponibile", "warn");
  if (u.remote_rev && u.remote_rev !== u.local_rev) return pill(u.ci_note || "in attesa dei test", "info");
  return pill("aggiornato", "ok");
}

export default function updates(root) {
  const facts = h("div");
  const news = h("pre", { class: "np-log" }, "…");
  const paint = (u) => {
    mount(facts, kv([
      ["Versione locale", mono(fmt.short(u.local_rev))],
      ["Versione remota", mono(fmt.short(u.remote_rev))],
      ["Con test superati", mono(fmt.short(u.target_rev))],
      ["Stato", state(u)],
      ["Ultimo controllo", fmt.when(u.last_check)],
      ["Ultimo esito", u.last_result || "—"],
    ]));
    news.textContent = u.changelog?.length ? u.changelog.join("\n") : "Nessuna novità in attesa.";
  };
  const check = async (quiet = false) => {
    const u = await api("/api/actions/update-check", { method: "POST" });
    paint(u);
    if (!quiet) toast(u.available ? "Aggiornamento disponibile" : "Atena è aggiornata");
  };
  mount(root,
    section("Aggiornamento autonomo da GitHub", facts,
      actions(
        button("Controlla ora", () => check()),
        button("Aggiorna ora", async () => {
          const r = await api("/api/actions/update-apply", { method: "POST" });
          toast(r.message || "Aggiornamento avviato");
        }, { kind: "primary", confirm: { title: "Applicare l'aggiornamento?", text: "Atena verrà riavviata e, in caso di problemi, ripristinata automaticamente.", action: "Aggiorna ora" } })),
      note("Atena controlla da sola GitHub, installa solo le versioni che hanno superato i test e torna indietro se qualcosa non va.")),
    section("Novità disponibili", news));
  check(true).catch((err) => { news.textContent = err.message; });
}
