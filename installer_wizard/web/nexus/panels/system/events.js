import { h, mount, onSnapshot, pill, section, table } from "../kit.js";

const TONE = { ERROR: "bad", WARN: "warn" };

export default function events(root) {
  const body = h("div");
  mount(root, section("Registro eventi", body));
  onSnapshot(root, (s) => mount(body, table(["Ora", "Livello", "Componente", "Evento"],
    (s.events || []).slice().reverse().map((e) => [
      h("span", { class: "mono" }, new Date(e.ts).toLocaleString(document.documentElement.lang || "it")),
      pill(e.level, TONE[e.level] || "ok"), h("span", { class: "mono" }, e.component), e.msg,
    ]), "Ancora nessun evento registrato.")));
}
