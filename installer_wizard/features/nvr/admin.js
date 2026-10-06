(() => {
  const A = window.AtenaAdmin, { $, fmt } = A;
  const LABELS = ["person", "car", "truck", "motorcycle", "bicycle", "dog", "cat", "bird", "package", "license_plate", "face", "motion"];
  const ICON = { person: "🧍", car: "🚗", truck: "🚚", motorcycle: "🏍️", bicycle: "🚲", dog: "🐕", cat: "🐈", bird: "🐦", package: "📦", license_plate: "🔢", face: "🙂", motion: "〰️" };
  const STATE = { connected: "ok", connecting: "running", error: "down", missing_dependency: "warn", disabled: "" };
  let bus = null, snapTimer = null, events = [], searching = false, settings = null;

  const when = (t) => new Date(t * 1000).toLocaleString(document.documentElement.lang || undefined, { dateStyle: "short", timeStyle: "medium" });
  const label = (l) => { const k = `nvr.label.${l}`, v = A.t(k); return v === k ? l : v; };
  const fail = (err) => A.toast(A.t(err.message), true);
  const size = (b) => (b > 1e9 ? `${(b / 1e9).toFixed(1)} GB` : `${(b / 1e6).toFixed(0)} MB`);

  function chips(id, selected) {
    $(id).innerHTML = LABELS.map((l) => `<label><input type="checkbox" value="${l}" ${selected.includes(l) ? "checked" : ""}>${ICON[l]} ${fmt.esc(label(l))}</label>`).join("");
  }
  const picked = (id) => [...$(id).querySelectorAll("input:checked")].map((x) => x.value);

  function renderStatus(s) {
    const ing = s.ingest, counts = Object.entries(s.counts_24h || {});
    const state = `<span class="badge ${STATE[ing.state] ?? ""}">${fmt.esc(A.t(`nvr.ingest.${ing.state}`))}</span>`;
    const summary = counts.length ? counts.map(([l, n]) => `${ICON[l] || "•"} ${n}`).join("  ") : A.t("nvr.no_events_24h");
    $("nv-status").innerHTML = `${state} · ${fmt.esc(A.t("nvr.last_24h"))}: ${fmt.esc(summary)}`;
  }

  function renderCameras(cams) {
    $("nv-cameras").innerHTML = cams.map((c) => `<div class="nv-cam">
      ${c.stream ? `<img alt="${fmt.esc(c.name)}" data-src="/api/cameras/live/${encodeURIComponent(c.id)}.jpg">` : ""}
      <div class="nv-meta"><b>${fmt.esc(c.name)}</b>
        <div class="faint">${c.recording ? `<span class="badge ok">${fmt.esc(A.t("nvr.recording"))}</span>` : `<span class="badge">${fmt.esc(A.t("nvr.not_recording"))}</span>`}
        ${c.segments ? ` · ${fmt.esc(A.t("nvr.segments", { n: c.segments, size: size(c.bytes) }))}` : ""}</div></div></div>`).join("")
      || `<div class="faint">${fmt.esc(A.t("nvr.no_cameras"))} <button class="btn sm" data-tab-open="cameras">${fmt.esc(A.t("nvr.open_cameras"))}</button></div>`;
    refreshSnapshots();
  }

  function refreshSnapshots() {
    document.querySelectorAll("#nv-cameras img[data-src]").forEach((img) => { img.src = `${img.dataset.src}?t=${Date.now()}`; });
  }

  function renderEvents(fresh) {
    $("nv-events").innerHTML = events.map((e) => `<div class="nv-ev ${fresh && e.id === fresh ? "fresh" : ""}">
      <span>${ICON[e.label] || "•"}</span>
      <div><b>${fmt.esc(label(e.label))}</b> · ${fmt.esc(e.camera)}${e.zone ? ` · ${fmt.esc(e.zone)}` : ""}
        <div class="faint">${fmt.esc(when(e.at))}${e.text ? ` · ${fmt.esc(e.text)}` : ""}</div></div>
      <span class="faint">${Math.round(e.score * 100)}%</span></div>`).join("")
      || `<div class="faint">${fmt.esc(A.t(searching ? "nvr.no_results" : "nvr.no_events"))}</div>`;
  }

  function fillSettings(s) {
    settings = s;
    $("nv-enabled").checked = s.enabled; $("nv-host").value = s.mqtt_host; $("nv-port").value = s.mqtt_port;
    $("nv-topic").value = s.mqtt_topic; $("nv-tls").checked = s.mqtt_tls; $("nv-user").value = s.mqtt_user;
    $("nv-pass").value = ""; $("nv-pass").placeholder = s.has_password ? A.t("nvr.password_set") : "";
    $("nv-retention").value = s.retention_days; $("nv-score").value = s.min_score;
    chips("nv-labels", s.labels); chips("nv-notify", s.notify_labels);
  }

  async function search(q) {
    searching = !!q.trim();
    try { events = (await A.api("GET", `/api/nvr/search?q=${encodeURIComponent(q)}&limit=100`)).events; renderEvents(); }
    catch (err) { fail(err); }
  }

  async function load() {
    try {
      const o = await A.api("GET", "/api/nvr/overview");
      renderStatus(o); renderCameras(o.cameras); fillSettings(o.settings);
      await search($("nv-query").value);
    } catch (err) { fail(err); }
    if (!bus) {
      bus = window.Atena.subscribeBus(["nvr.status", "nvr.event.>"], (env) => {
        if (env.topic === "nvr.status") return renderStatus(env.payload);
        if (searching) return;
        events = [env.payload, ...events.filter((e) => e.id !== env.payload.id)].slice(0, 100);
        renderEvents(env.payload.id);
      }, (up) => { $("nv-live").classList.toggle("ok", up); });
    }
    clearInterval(snapTimer); snapTimer = setInterval(() => { if (A.isOn("nvr")) refreshSnapshots(); }, 5000);
  }

  function leave() { clearInterval(snapTimer); if (bus) { bus.close(); bus = null; } }

  function init() {
    $("nv-cameras").addEventListener("click", (e) => { const b = e.target.closest("[data-tab-open]"); if (b) A.openTab(b.dataset.tabOpen); });
    $("nv-search").addEventListener("submit", (e) => { e.preventDefault(); search($("nv-query").value); });
    $("nv-settings").addEventListener("submit", async (e) => {
      e.preventDefault();
      const body = { enabled: $("nv-enabled").checked, mqtt_host: $("nv-host").value, mqtt_port: Number($("nv-port").value),
        mqtt_topic: $("nv-topic").value, mqtt_tls: $("nv-tls").checked, mqtt_user: $("nv-user").value,
        retention_days: Number($("nv-retention").value), min_score: Number($("nv-score").value),
        labels: picked("nv-labels"), notify_labels: picked("nv-notify") };
      if ($("nv-pass").value) body.mqtt_password = $("nv-pass").value;
      try { fillSettings(await A.api("PUT", "/api/nvr/settings", body)); A.toast(A.t("nvr.saved")); } catch (err) { fail(err); }
    });
    $("nv-clear").addEventListener("click", async () => {
      if (!confirm(A.t("nvr.confirm_clear"))) return;
      try { await A.api("DELETE", "/api/nvr/events"); events = []; renderEvents(); } catch (err) { fail(err); }
    });
    window.addEventListener("atena-i18n", () => { if (A.isOn("nvr") && settings) { fillSettings(settings); renderEvents(); } });
  }

  A.tab("nvr", { title: "NVR", init, load, leave });
})();
