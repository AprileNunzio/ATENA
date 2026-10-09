(() => {
  const A = window.AtenaAdmin, KEY = "atena_ui_mode", MODES = ["simple", "expert"];
  const nexusMode = () => {
    try { const level = localStorage.getItem("nexus.level"); return level ? (level === "explorer" ? "simple" : "expert") : null; } catch { return null; }
  };
  const read = () => {
    if (document.documentElement.classList.contains("embedded")) { const mode = nexusMode(); if (mode) return mode; }
    try { const v = localStorage.getItem(KEY); return MODES.includes(v) ? v : "simple"; } catch { return "simple"; }
  };

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
    const bar = document.querySelector(".topbar .row");
    if (!bar || document.getElementById("ui-mode")) return;
    const box = document.createElement("div");
    box.id = "ui-mode"; box.className = "seg ui-mode";
    box.innerHTML = '<button type="button" data-ui-mode="simple" title="Interfaccia essenziale e guidata">Semplice</button><button type="button" data-ui-mode="expert" title="Tutti i dettagli, le priorità e le impostazioni avanzate">Esperto</button>';
    box.addEventListener("click", (e) => { const b = e.target.closest("[data-ui-mode]"); if (b) A.uiMode.set(b.dataset.uiMode); });
    bar.prepend(box);
    document.addEventListener("click", (e) => { const b = e.target.closest("[data-ui-mode-set]"); if (b) A.uiMode.set(b.dataset.uiModeSet); });
    apply(read());
  }

  apply(read());
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount); else mount();
})();
