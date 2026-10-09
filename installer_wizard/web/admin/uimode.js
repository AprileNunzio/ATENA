(() => {
  const A = window.AtenaAdmin, KEY = "atena_ui_mode", MODES = ["simple", "expert"];
  const read = () => { try { const v = localStorage.getItem(KEY); return MODES.includes(v) ? v : "simple"; } catch { return "simple"; } };

  function apply(mode) {
    document.body.classList.toggle("ui-expert", mode === "expert");
    document.body.classList.toggle("ui-simple", mode !== "expert");
    document.querySelectorAll("[data-ui-mode]").forEach((b) => b.classList.toggle("on", b.dataset.uiMode === mode));
  }

  A.uiMode = {
    get: read,
    expert: () => read() === "expert",
    set(mode) {
      if (!MODES.includes(mode)) return;
      try { localStorage.setItem(KEY, mode); } catch { A.toast("Preferenza non salvata nel browser", true); }
      apply(mode);
      document.dispatchEvent(new CustomEvent("atena:uimode", { detail: mode }));
    },
  };

  function mount() {
    const nav = document.querySelector("nav .spacer");
    if (!nav || document.getElementById("ui-mode")) return;
    const box = document.createElement("div");
    box.id = "ui-mode"; box.className = "seg ui-mode";
    box.innerHTML = '<button type="button" data-ui-mode="simple" title="Interfaccia essenziale e guidata">Semplice</button><button type="button" data-ui-mode="expert" title="Tutti i dettagli, le priorità e le impostazioni avanzate">Esperto</button>';
    box.addEventListener("click", (e) => { const b = e.target.closest("[data-ui-mode]"); if (b) A.uiMode.set(b.dataset.uiMode); });
    nav.after(box);
    apply(read());
  }

  apply(read());
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount); else mount();
})();
