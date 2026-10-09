import { h } from "../../core/dom.js";

const SAFE_LINK = /^\/(?!\/)[\w\-./?=&%]*$/;

export function fieldFor(setting, value, id) {
  const common = { id, name: setting.key, class: "input", autocomplete: "off" };
  switch (setting.type) {
    case "select":
    case "bool":
      return h("select", common, (setting.options || []).map((o) =>
        h("option", { value: o.value, selected: String(value) === o.value ? true : null }, o.label)));
    case "number":
      return h("input", { ...common, type: "number", inputmode: "decimal", step: "any", value: value ?? "" });
    case "secret":
      return h("input", { ...common, type: "password", autocomplete: "new-password", placeholder: value ? `Salvata (${value})` : "Non impostata", value: "" });
    case "color":
      return h("input", { ...common, type: "color", class: "input color", value: /^#[0-9a-f]{6}$/i.test(value) ? value : "#29e0ff" });
    case "link":
      return SAFE_LINK.test(String(setting.default || ""))
        ? h("a", { class: "btn", href: setting.default, download: setting.download ? "" : null }, setting.button || "Apri")
        : h("span", { class: "dim" }, "Collegamento non disponibile");
    default:
      return h("input", { ...common, type: "text", maxlength: "500", placeholder: setting.placeholder || "", value: value ?? "" });
  }
}

export function readField(setting, input) {
  if (!input || setting.type === "link") return undefined;
  const value = input.value.trim();
  if (setting.type === "secret" && !value) return undefined;
  if (value.includes("\n") || value.length > 500) throw new Error(`Valore troppo lungo per «${setting.label}»`);
  return value;
}
