(() => {
  const A = window.AtenaAdmin, { $, fmt } = A;
  const POLL = 1500;
  const AREAS = [
    ["home_assistant", 0x3dffa8], ["brain", 0xa08cff], ["sports", 0xffc43d], ["tv", 0xff7ac8], ["google", 0x29e0ff],
    ["people", 0x6ea8ff], ["automations", 0xff8c3c], ["music", 0x3dffa8], ["cameras", 0xff4d6a], ["chat", 0x29e0ff],
    ["places", 0xa08cff], ["nodes", 0x6ea8ff],
  ];
  const SLOTS = [[-20, -22], [-12, -24], [12, -24], [20, -22], [-26, -12], [26, -12], [-26, -2], [26, -2], [-20, 18], [-8, 20], [8, 20], [20, 18]];
  let world = null, fleet = null, office = null, timer = 0, seq = -1, data = null, failed = false;

  function areas() {
    const feats = (A.featData && A.featData.features) || [];
    return AREAS.map(([id, color]) => [feats.find((f) => f.id === id && f.panel), color]).filter(([f]) => f)
      .map(([f, color], i) => ({ feature: f.id, tab: f.panel, title: A.t(`feature.${f.id}`) !== `feature.${f.id}` ? A.t(`feature.${f.id}`) : f.name,
        icon: f.icon || "◆", color, x: SLOTS[i][0], z: SLOTS[i][1], h: 2.4 + (i % 3) * 0.9 }));
  }

  function tiles() {
    $("hub-tiles").innerHTML = areas().map((a) => `<button type="button" class="hub-tile" data-feature="${fmt.esc(a.feature)}" style="--c:#${a.color.toString(16).padStart(6, "0")}">
      <span class="hub-tile-ic">${fmt.esc(a.icon)}</span><span>${fmt.esc(a.title)}</span></button>`).join("");
  }

  function sentence(d) {
    const people = d.presence.people.filter((p) => p.known).map((p) => p.name);
    const busy = d.desks.filter((x) => x.busy).length;
    const parts = [d.health.down.length ? `${d.health.down.length} componenti da controllare` : "tutto funziona"];
    parts.push(people.length ? `in casa: ${people.join(", ")}` : "nessuno riconosciuto davanti allo schermo");
    if (busy) parts.push(`${busy} agenti al lavoro`);
    return parts.join(" · ");
  }

  function live(d) {
    const j = d.journeys[0];
    const busy = d.desks.filter((x) => x.busy);
    const flow = j ? `<div class="hub-live-q">❝ ${fmt.esc(j.query)} ❞</div>
      <ol class="hub-steps">${d.stations.map((s, i) => `<li class="${i < j.reached ? "done" : i === j.reached ? (j.state === "running" ? "now" : j.failed ? "bad" : "done") : ""}">${fmt.esc(s.label)}</li>`).join("")}</ol>`
      : '<div class="muted-note">Nessuna domanda in viaggio: chiedi qualcosa qui sopra.</div>';
    const agents = busy.length ? busy.map((x) => `<div class="hub-agent"><b>${fmt.esc(x.label)}</b><span>${fmt.esc(x.doing || "al lavoro")}${x.model ? ` · ${fmt.esc(x.model)}` : ""}</span></div>`).join("")
      : '<div class="muted-note">Tutti gli agenti sono in attesa nel salottino.</div>';
    return `<div class="hub-live-title">Flusso cognitivo</div>${flow}<div class="hub-live-title">Agenti</div>${agents}`;
  }

  function flat(d) {
    const j = d.journeys[0];
    return `<div class="hub-flat-road">${d.stations.map((s, i) => `<span class="${j && i <= j.reached ? "on" : ""}">${fmt.esc(s.label)}</span>`).join("")}</div>
      <div class="hub-flat-desks">${d.desks.map((x) => `<span class="${x.busy ? "on" : ""}">${x.busy ? "🪑" : "☕"} ${fmt.esc(x.label)}</span>`).join("")}</div>`;
  }

  async function build(d) {
    if (world || failed) return;
    if (!A.hubWorld.supported()) { failed = true; return; }
    try { await A.hubWorld.libraries(); } catch (e) { failed = true; A.toast(e.message, true); return; }
    world = A.hubWorld.create($("hub-canvas"), { stations: d.stations, districts: areas(), still: window.matchMedia("(prefers-reduced-motion: reduce)").matches,
      onPick: (a) => A.openFeature(a.feature) });
    fleet = new A.hubFleet.Fleet(world, d.stations);
    office = new A.hubOffice.Office(world);
    if (A.isOn("hub")) world.start();
  }

  async function poll() {
    clearTimeout(timer);
    if (!A.isOn("hub")) { if (world) world.stop(); return; }
    try {
      const d = await A.api("GET", "/api/hub");
      data = d;
      $("hub-status").textContent = sentence(d);
      $("hub-live").innerHTML = live(d);
      await build(d);
      document.getElementById("tab-hub").classList.toggle("flat", failed);
      if (failed) $("hub-flat").innerHTML = flat(d);
      if (d.seq !== seq && world) { seq = d.seq; fleet.sync(d.journeys); office.sync(d.desks); }
    } catch (e) { $("hub-status").textContent = e.message; }
    timer = setTimeout(poll, POLL);
  }

  async function ask(e) {
    e.preventDefault();
    const text = $("hub-q").value.trim();
    if (!text) return;
    $("hub-q").value = ""; $("hub-answer").textContent = "…";
    setTimeout(poll, 300);
    try { const r = await A.api("POST", "/api/assistant/chat", { text }); $("hub-answer").textContent = r.reply || ""; }
    catch (err) { $("hub-answer").textContent = err.message; }
  }

  function greet() {
    const h = new Date().getHours();
    $("hub-hello").textContent = h < 12 ? "Buongiorno" : h < 18 ? "Buon pomeriggio" : "Buonasera";
  }

  function init() {
    $("hub-ask").addEventListener("submit", ask);
    $("hub-tiles").addEventListener("click", (e) => { const b = e.target.closest("[data-feature]"); if (b) A.openFeature(b.dataset.feature); });
    document.addEventListener("visibilitychange", () => { if (!world) return; if (document.hidden) world.stop(); else if (A.isOn("hub")) world.start(); });
  }

  function load() {
    greet(); tiles();
    if (world) world.start();
    poll();
  }

  function leave() { if (world) world.stop(); clearTimeout(timer); }

  A.hub = { leave, data: () => data };
  A.tab("hub", { title: "Plancia", init, load });
})();
