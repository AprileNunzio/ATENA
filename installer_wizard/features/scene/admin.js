(() => {
  const A = window.AtenaAdmin, { $, fmt } = A;
  const OK = { ok: "ok", with_person: "ok", elsewhere: "warn", stale: "warn", unknown: "down" };
  let data = null, points = [], bus = null;

  const esc = fmt.esc;
  const fail = (err) => A.toast(A.t(err.message), true);
  const objectName = (label) => { const k = `scene.object.${label}`, v = A.t(k); return v === k ? label : v; };
  const ago = (t) => {
    const m = Math.floor((Date.now() / 1000 - t) / 60);
    return m < 1 ? A.t("scene.ago.now") : m < 60 ? A.t("scene.ago.minutes", { n: m }) : A.t("scene.ago.hours", { n: Math.floor(m / 60) });
  };
  const list = (text) => text.split(",").map((s) => s.trim()).filter(Boolean);

  function seenText(seen) {
    if (!seen) return A.t("scene.never_seen");
    const where = seen.held ? A.t("scene.held_by", { who: seen.holder || A.t("scene.someone") })
      : seen.anchor_name || seen.room || A.t("scene.in_view");
    return `${where} · ${ago(seen.at)}`;
  }

  function renderPresence(f) {
    $("sc-presence").innerHTML = (f.people || []).map((p) => `<div class="sc-item"><div><b>${esc(p.name)}</b>
      <span class="badge ${p.present ? "ok" : ""}">${esc(A.t(p.present ? "scene.present" : "scene.absent"))}</span>
      <div class="faint">${p.sources.map((s) => esc(A.t(`scene.source.${s}`))).join(" · ") || "—"}</div>
      <div class="sc-bar"><i style="width:${Math.round(p.probability * 100)}%"></i></div></div>
      <span class="faint">${Math.round(p.probability * 100)}%</span></div>`).join("") || `<div class="faint">${esc(A.t("scene.nobody"))}</div>`;
  }

  function renderItems() {
    $("sc-items").innerHTML = data.items.map((i) => `<div class="sc-item"><div><b>${esc(i.name)}</b>
      <span class="faint">(${i.labels.map((l) => esc(objectName(l))).join(", ")})</span><div class="faint">${esc(seenText(i.seen))}</div></div>
      <button class="btn sm danger" data-del="item" data-id="${esc(i.id)}">${esc(A.t("scene.remove"))}</button></div>`).join("")
      || `<div class="faint">${esc(A.t("scene.no_items"))}</div>`;
    $("sc-item-label").innerHTML = data.labels.map((l) => `<option value="${esc(l)}">${esc(objectName(l))}</option>`).join("");
  }

  function renderAnchors() {
    $("sc-anchors").innerHTML = data.anchors.map((a) => `<div class="sc-item"><div><b>${esc(a.name)}</b>${a.entrance ? ` <span class="badge">${esc(A.t("scene.entrance"))}</span>` : ""}
      <div class="faint">${esc(a.room || "—")}${a.x !== null ? ` · (${a.x}, ${a.y}, ${a.z}) m` : ""}</div></div>
      <button class="btn sm danger" data-del="anchor" data-id="${esc(a.id)}">${esc(A.t("scene.remove"))}</button></div>`).join("")
      || `<div class="faint">${esc(A.t("scene.no_anchors"))}</div>`;
    drawShapes();
  }

  function renderProfiles() {
    $("sc-profiles").innerHTML = data.profiles.map((p) => `<div class="sc-item"><div><b>${esc(p.name)}</b>
      <span class="badge ${p.status.ready ? "ok" : "warn"}">${esc(A.t(p.status.ready ? "scene.ready" : "scene.not_ready"))}</span>
      ${p.status.checks.map((c) => `<div class="faint"><span class="badge ${OK[c.status]}">${esc(A.t(`scene.status.${c.status}`))}</span> ${esc(c.item)} · ${esc(seenText(c.seen))}</div>`).join("")}</div>
      <button class="btn sm danger" data-del="profile" data-id="${esc(p.id)}">${esc(A.t("scene.remove"))}</button></div>`).join("")
      || `<div class="faint">${esc(A.t("scene.no_profiles"))}</div>`;
    $("sc-reqs").innerHTML = data.items.map((i) => `<label class="sc-req"><input type="checkbox" data-req="${esc(i.id)}"><span>${esc(i.name)}</span>
      <select data-anchor><option value="">${esc(A.t("scene.anywhere"))}</option>${data.anchors.map((a) => `<option value="${esc(a.id)}">${esc(a.name)}</option>`).join("")}</select>
      <span class="switch"><input type="checkbox" data-entrance>${esc(A.t("scene.entrance"))}</span>
      <input type="number" min="1" max="10080" value="720" data-age title="${esc(A.t("scene.max_age"))}"></label>`).join("")
      || `<div class="faint">${esc(A.t("scene.items_first"))}</div>`;
  }

  function drawShapes() {
    const poly = (pts, cls) => `<polygon class="${cls}" points="${pts.map((p) => p.join(",")).join(" ")}"/>`;
    $("sc-svg").innerHTML = data.anchors.filter((a) => a.source === "main").map((a) => poly(a.polygon, "saved")).join("")
      + (points.length >= 3 ? poly(points, "") : "") + points.map(([x, y]) => `<circle cx="${x}" cy="${y}" r="0.008"/>`).join("");
  }

  function render() { renderItems(); renderAnchors(); renderProfiles(); renderPresence(data.fusion); }

  async function load() {
    try { data = await A.api("GET", "/api/scene"); render(); } catch (err) { fail(err); }
    $("sc-snapshot").src = `/api/vision/snapshot.jpg?t=${Date.now()}`;
    if (!bus) bus = window.Atena.subscribeBus("fusion.presence", (env) => renderPresence(env.payload));
  }

  async function save(kind, body) {
    try { await A.api("POST", `/api/scene/${kind}`, body); A.toast(A.t("scene.saved")); await load(); return true; }
    catch (err) { fail(err); return false; }
  }

  function init() {
    document.querySelector("#tab-scene .sc-canvas").addEventListener("click", (e) => {
      const r = e.currentTarget.getBoundingClientRect();
      if (points.length >= 16) return;
      points.push([+((e.clientX - r.left) / r.width).toFixed(4), +((e.clientY - r.top) / r.height).toFixed(4)]);
      drawShapes();
    });
    $("sc-clear-points").addEventListener("click", () => { points = []; drawShapes(); });
    $("sc-refresh-shot").addEventListener("click", () => { $("sc-snapshot").src = `/api/vision/snapshot.jpg?t=${Date.now()}`; });
    $("sc-anchor-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      if (points.length < 3) return A.toast(A.t("scene.error.polygon"), true);
      const num = (id) => ($(id).value === "" ? null : Number($(id).value));
      if (await save("anchor", { name: $("sc-anchor-name").value, room: $("sc-anchor-room").value, source: "main", polygon: points,
        x: num("sc-x"), y: num("sc-y"), z: num("sc-z"), entrance: $("sc-entrance").checked })) { points = []; $("sc-anchor-form").reset(); }
    });
    $("sc-item-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      if (await save("item", { name: $("sc-item-name").value, labels: [$("sc-item-label").value], aliases: list($("sc-item-aliases").value) })) $("sc-item-form").reset();
    });
    $("sc-profile-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const requirements = [...$("sc-reqs").querySelectorAll(".sc-req")].filter((r) => r.querySelector("[data-req]").checked).map((r) => ({
        item: r.querySelector("[data-req]").dataset.req, anchor: r.querySelector("[data-anchor]").value,
        near_entrance: r.querySelector("[data-entrance]").checked, max_age_min: Number(r.querySelector("[data-age]").value) }));
      if (await save("profile", { name: $("sc-profile-name").value, aliases: list($("sc-profile-aliases").value), requirements })) $("sc-profile-form").reset();
    });
    $("tab-scene").addEventListener("click", async (e) => {
      const b = e.target.closest("[data-del]"); if (!b) return;
      if (!confirm(A.t("scene.confirm_remove"))) return;
      try { await A.api("DELETE", `/api/scene/${b.dataset.del}/${encodeURIComponent(b.dataset.id)}`); await load(); } catch (err) { fail(err); }
    });
    window.addEventListener("atena-i18n", () => { if (data && A.isOn("scene")) render(); });
  }

  A.tab("scene", { title: "Scena e presenza", init, load, leave() { if (bus) { bus.close(); bus = null; } } });
})();
