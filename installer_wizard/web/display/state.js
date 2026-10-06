(() => {
  const $ = (id) => document.getElementById(id);
  const D = window.AtenaDisplay = {
    $,
    fmt: Atena.fmt,
    FACE: window.ATENA_FACE || {},
    local: ["127.0.0.1", "localhost"].includes(location.hostname),
    avatar: null,
    scene: null,
    look: null,
    userName: "",
    mode: "face",
    voiceOn: true,
    busy: false,
    lastInteraction: Date.now(),
    selectedId: null,
    lastGreeting: null,
    presentNames: [],
    lastVoice: false,
    stageZone: null,
    regions: () => (window.Atena3D ? Atena3D.REGIONS : {}),
  };

  let typer;
  D.typeInto = (el, text) => {
    clearInterval(typer); el.textContent = ""; let i = 0;
    typer = setInterval(() => { el.textContent = text.slice(0, i += 2); if (i >= text.length) clearInterval(typer); }, 22);
  };

  let lastPing = 0;
  D.pingActivity = (force) => {
    if (!force && Date.now() - lastPing < 20000) return;
    lastPing = Date.now();
    fetch("/api/activity", { method: "POST" }).catch(() => {});
  };
})();
