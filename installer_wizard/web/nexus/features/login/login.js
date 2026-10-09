import { h, mount } from "../../core/dom.js";
import { api } from "../../core/http.js";
import { Orb } from "../../components/orb.js";

export function renderLogin(root, onSuccess) {
  const canvas = h("canvas", { "aria-hidden": "true" });
  const user = h("input", { class: "input", id: "nx-user", name: "username", autocomplete: "username", required: true, maxlength: "64", autocapitalize: "none", spellcheck: "false" });
  const pass = h("input", { class: "input", id: "nx-pass", name: "password", type: "password", autocomplete: "current-password", required: true, maxlength: "256" });
  const error = h("p", { class: "login-err", role: "alert" });
  const submit = h("button", { class: "btn primary", type: "submit" }, "Accedi");
  const card = h("div", { class: "panel login-card" },
    h("div", { class: "orb-box" }, canvas),
    h("h1", {}, "A.T.E.N.A.", h("small", {}, "NEXUS · PANNELLO DI CONTROLLO")),
    h("form", { onsubmit: send, novalidate: false },
      h("div", { class: "field" }, h("label", { for: "nx-user" }, "Utente di sistema"), user),
      h("div", { class: "field" }, h("label", { for: "nx-pass" }, "Password"), pass),
      error, submit),
    h("p", { class: "hint" }, "Accesso consentito a root e agli utenti dei gruppi sudo o atena-admin."),
    h("p", { class: "hint" }, h("a", { href: "/classic" }, "Apri il pannello classico")));
  mount(root, h("main", { class: "login" }, card));
  const orb = new Orb(canvas);
  orb.start();
  user.focus();

  async function send(event) {
    event.preventDefault();
    error.textContent = "";
    submit.disabled = true;
    orb.setState("busy");
    try {
      const result = await api("/api/auth/login", { method: "POST", body: { username: user.value.trim(), password: pass.value } });
      pass.value = "";
      orb.stop();
      onSuccess(result.user);
    } catch (err) {
      pass.value = "";
      error.textContent = err.message;
      orb.setState("bad");
      card.classList.remove("shake");
      void card.offsetWidth;
      card.classList.add("shake");
      pass.focus();
      setTimeout(() => orb.setState("ok"), 1600);
    } finally {
      submit.disabled = false;
    }
  }
}
