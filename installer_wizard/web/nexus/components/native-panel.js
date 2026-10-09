import { h, mount } from "../core/dom.js";
import { hasPanel, loadPanel } from "../panels/registry.js";
import { failure, loading } from "../panels/kit.js";

export { hasPanel };

export function nativePanel(id, ctx = {}) {
  const root = h("div", { class: "np", "data-panel": id });
  const start = () => {
    mount(root, loading());
    loadPanel(id)
      .then((module) => { mount(root); return module.default(root, { id, ...ctx }); })
      .catch((err) => mount(root, failure(err, start)));
  };
  if (!hasPanel(id)) return mount(root, failure(new Error("Pannello non disponibile")));
  start();
  return root;
}
