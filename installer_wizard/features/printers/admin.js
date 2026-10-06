(() => {
  const A = window.AtenaAdmin, { $, fmt } = A;
  const STATE = { ready: "ok", standby: "warn", busy: "running", offline: "down", unknown: "" };
  let data = { printers: [] }, editing = null;

  const typeLabel = (t) => A.t(`printers.type.${t}`);
  const stateBadge = (s) => {
    const key = `printers.state.${s}`, label = A.t(key);
    return `<span class="badge ${STATE[s] ?? ""}">${fmt.esc(label === key ? s : label)}</span>`;
  };
  const fail = (err) => A.toast(A.t(err.message), true);

  function render() {
    $("pr-list").innerHTML = data.printers.map((p) => `<div class="pr-item" data-id="${fmt.esc(p.id)}">
      <div><b>${fmt.esc(p.name)}</b> <span class="badge">${fmt.esc(typeLabel(p.type))}</span> ${stateBadge(p.status || "unknown")}
        ${p.atena_default ? `<span class="badge ok">${fmt.esc(A.t("printers.default"))}</span>` : ""}
        <div class="faint">${fmt.esc(A.t(`printers.connection.${p.connection}`))}${p.address ? " · " + fmt.esc(p.address) : ""}${p.port ? ":" + fmt.esc(String(p.port)) : ""}</div>
        <div class="faint" data-probe></div></div>
      <div class="actions">
        <button class="btn sm" data-act="probe">${fmt.esc(A.t("printers.probe_btn"))}</button>
        <button class="btn sm" data-act="options">${fmt.esc(A.t("printers.options"))}</button>
        ${p.custom ? `<button class="btn sm danger" data-act="remove">${fmt.esc(A.t("printers.remove"))}</button>` : ""}
      </div></div>`).join("") || `<div class="faint">${fmt.esc(A.t("printers.empty"))}</div>`;
  }

  async function load() {
    try { data = await A.api("GET", "/api/printers/list"); render(); } catch (err) { fail(err); }
  }

  function showOptions(p) {
    editing = p.id;
    const o = p.options;
    $("pr-options-title").textContent = A.t("printers.options_for", { name: p.name });
    $("po-paper").value = o.paper; $("po-orientation").value = o.orientation; $("po-quality").value = o.quality;
    $("po-copies").value = o.copies; $("po-color").checked = o.color; $("po-duplex").checked = o.duplex;
    $("po-power").value = o.laser_power; $("po-feed").value = o.laser_feed; $("po-nozzle").value = o.nozzle_temp; $("po-bed").value = o.bed_temp;
    $("po-default").checked = !!p.atena_default;
    document.querySelectorAll("#pr-options-form .pr-2d").forEach((x) => { x.hidden = !["laser_2d", "inkjet_2d"].includes(p.type); });
    document.querySelectorAll("#pr-options-form .pr-laser").forEach((x) => { x.hidden = p.type !== "engraver"; });
    document.querySelectorAll("#pr-options-form .pr-3d").forEach((x) => { x.hidden = p.type !== "3d"; });
    $("pr-options-panel").hidden = false;
    $("pr-options-panel").scrollIntoView({ behavior: "smooth" });
  }

  async function discover() {
    $("pr-discover-panel").hidden = false;
    $("pr-found").innerHTML = `<div class="faint">${fmt.esc(A.t("printers.searching"))}</div>`;
    try {
      const r = await A.api("POST", "/api/printers/discover");
      $("pr-found").innerHTML = r.devices.map((d) => `<div class="pr-item" data-uri="${fmt.esc(d.uri)}" data-host="${fmt.esc(d.host || "")}" data-port="${fmt.esc(String(d.port || ""))}">
        <div><b>${fmt.esc(d.label)}</b><div class="faint">${fmt.esc(d.uri)}</div></div>
        <div class="actions">${d.host ? `<button class="btn sm" data-act="use">${fmt.esc(A.t("printers.use"))}</button>` : ""}
          ${r.can_install && /^ipps?:/.test(d.uri) ? `<button class="btn sm primary" data-act="install">${fmt.esc(A.t("printers.install"))}</button>` : ""}</div></div>`).join("")
        || `<div class="faint">${fmt.esc(A.t("printers.none_found"))}</div>`;
    } catch (err) { $("pr-found").innerHTML = ""; fail(err); }
  }

  function init() {
    $("pr-refresh").addEventListener("click", load);
    $("pr-discover").addEventListener("click", discover);
    $("pr-add-open").addEventListener("click", () => { $("pr-add-form").reset(); $("pr-add-panel").hidden = false; $("pr-name").focus(); });
    $("pr-add-cancel").addEventListener("click", () => { $("pr-add-panel").hidden = true; });
    $("pr-options-cancel").addEventListener("click", () => { $("pr-options-panel").hidden = true; editing = null; });
    $("pr-type").addEventListener("change", () => { $("pr-port").value = $("pr-type").value === "3d" ? 7125 : 9100; });
    $("pr-add-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        await A.api("POST", "/api/printers/add", { name: $("pr-name").value, type: $("pr-type").value, connection: $("pr-conn").value,
          address: $("pr-address").value, port: Number($("pr-port").value), api_key: $("pr-key").value });
        $("pr-add-panel").hidden = true; A.toast(A.t("printers.saved")); load();
      } catch (err) { fail(err); }
    });
    $("pr-options-form").addEventListener("submit", async (e) => {
      e.preventDefault(); if (!editing) return;
      try {
        await A.api("PUT", `/api/printers/${encodeURIComponent(editing)}/options`, {
          paper: $("po-paper").value, orientation: $("po-orientation").value, quality: $("po-quality").value,
          copies: Number($("po-copies").value), color: $("po-color").checked, duplex: $("po-duplex").checked,
          laser_power: Number($("po-power").value), laser_feed: Number($("po-feed").value),
          nozzle_temp: Number($("po-nozzle").value), bed_temp: Number($("po-bed").value), atena_default: $("po-default").checked });
        $("pr-options-panel").hidden = true; editing = null; A.toast(A.t("printers.saved")); load();
      } catch (err) { fail(err); }
    });
    $("pr-list").addEventListener("click", async (e) => {
      const b = e.target.closest("[data-act]"), item = e.target.closest("[data-id]"); if (!b || !item) return;
      const p = data.printers.find((x) => x.id === item.dataset.id); if (!p) return;
      if (b.dataset.act === "options") return showOptions(p);
      if (b.dataset.act === "remove") {
        if (!confirm(A.t("printers.confirm_remove", { name: p.name }))) return;
        try { await A.api("POST", "/api/printers/remove", { id: p.id }); load(); } catch (err) { fail(err); }
        return;
      }
      const out = item.querySelector("[data-probe]"); out.textContent = A.t("printers.probing");
      try { const r = await A.api("POST", `/api/printers/${encodeURIComponent(p.id)}/probe`); out.innerHTML = `${stateBadge(r.state)} ${fmt.esc(A.t(r.detail))}`; }
      catch (err) { out.textContent = A.t(err.message); }
    });
    $("pr-found").addEventListener("click", async (e) => {
      const b = e.target.closest("[data-act]"), item = e.target.closest("[data-uri]"); if (!b || !item) return;
      if (b.dataset.act === "use") {
        $("pr-add-form").reset(); $("pr-add-panel").hidden = false;
        $("pr-address").value = item.dataset.host; $("pr-port").value = item.dataset.port === "631" ? 631 : 9100; $("pr-name").focus();
        return;
      }
      const queue = prompt(A.t("printers.queue_prompt"), (item.dataset.host || "atena").replace(/[^A-Za-z0-9_-]/g, "_"));
      if (!queue) return;
      try { await A.api("POST", "/api/printers/install", { uri: item.dataset.uri, queue }); A.toast(A.t("printers.installed", { queue })); load(); }
      catch (err) { fail(err); }
    });
    window.addEventListener("atena-i18n", () => { if (A.isOn("printers")) render(); });
  }

  A.tab("printers", { title: "Stampanti", init, load });
})();
