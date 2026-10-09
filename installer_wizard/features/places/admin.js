(() => {
  const A = window.AtenaAdmin, { $, fmt } = A;
  const SENSES = { sees: "vede", hears: "sente", shows: "mostra", speaks: "parla" };
  const ICONS = { atena: "🧠", phone: "📱", pc: "💻", display: "🖥", satellite: "🔊", camera: "📷", other: "📟" };
  let data = null, timer = null;

  async function call(method, url, body) {
    try { data = await A.api(method, url, body); render(); return data; } catch (e) { A.toast(e.message, true); return null; }
  }

  function roomOptions(selected) {
    const byFloor = data.floors.map((f) => {
      const rooms = data.rooms.filter((r) => r.floor_id === f.id);
      return rooms.length ? `<optgroup label="${fmt.esc(f.name)}">${rooms.map((r) => `<option value="${fmt.esc(r.id)}" ${r.id === selected ? "selected" : ""}>${fmt.esc(r.name)}</option>`).join("")}</optgroup>` : "";
    }).join("");
    const loose = data.rooms.filter((r) => !data.floors.some((f) => f.id === r.floor_id));
    return `<option value="">— nessuna stanza —</option>${byFloor}${loose.map((r) => `<option value="${fmt.esc(r.id)}" ${r.id === selected ? "selected" : ""}>${fmt.esc(r.name)}</option>`).join("")}`;
  }

  function floorCard(floor) {
    const rooms = data.rooms.filter((r) => (floor ? r.floor_id === floor.id : !data.floors.some((f) => f.id === r.floor_id)));
    if (!floor && !rooms.length) return "";
    const devices = (rid) => data.devices.filter((d) => d.room_id === rid).map((d) => ICONS[d.kind] || "📟").join(" ");
    const people = (rid) => data.people.filter((p) => p.room_id === rid).map((p) => `<span class="badge">${fmt.esc(p.name)}</span>`).join(" ");
    return `<div class="panel pl-floor" data-floor="${floor ? fmt.esc(floor.id) : ""}">
      <div class="row" style="justify-content:space-between; flex-wrap:wrap; gap:8px">
        <div class="panel-title">${floor ? `${fmt.esc(floor.name)} <span class="faint">livello ${floor.level}</span>` : "Stanze senza piano"}</div>
        ${floor ? `<div class="actions"><button class="btn sm" data-floor-edit>Rinomina</button><button class="btn sm danger" data-floor-del>Elimina</button></div>` : ""}
      </div>
      <div class="pl-rooms">${rooms.map((r) => `<div class="pl-room" data-room="${fmt.esc(r.id)}">
        <div><b>${fmt.esc(r.name)}</b>${r.ha_area ? ' <span class="faint">· Home Assistant</span>' : ""}</div>
        <div class="pl-room-icons">${devices(r.id) || '<span class="faint">nessun dispositivo</span>'}</div>
        <div>${people(r.id)}</div>
        <div class="actions"><button class="btn sm" data-room-edit>Rinomina</button><button class="btn sm danger" data-room-del>Elimina</button></div></div>`).join("")}
        ${floor ? `<form class="pl-inline" data-room-add><input name="name" placeholder="Nuova stanza (es. Studio)" maxlength="40" required><button class="btn sm primary" type="submit">Aggiungi</button></form>` : ""}
      </div></div>`;
  }

  function deviceRows() {
    const rows = data.devices.map((d) => `<tr data-key="${fmt.esc(d.key)}">
      <td>${ICONS[d.kind] || "📟"} ${fmt.esc(d.name)}${d.hint ? `<div class="faint">indicata: ${fmt.esc(d.hint)}</div>` : ""}</td>
      <td><select data-room>${roomOptions(d.room_id)}</select></td>
      <td class="pl-senses">${Object.entries(SENSES).map(([k, label]) => `<label class="switch"><input type="checkbox" data-sense="${k}" ${d.senses.includes(k) ? "checked" : ""}> ${fmt.esc(label)}</label>`).join("")}</td></tr>`);
    return `<table class="pl-table"><thead><tr><th>Dispositivo</th><th>Stanza</th><th>Cosa fa</th></tr></thead><tbody>${rows.join("")}</tbody></table>`;
  }

  function render() {
    if (!data) return;
    $("pl-people").innerHTML = data.people.length ? data.people.map((p) => `<span class="badge">${fmt.esc(p.name)}: ${fmt.esc(p.room)}</span>`).join(" ")
      : '<span class="faint">In questo momento non so in che stanza si trovi nessuno.</span>';
    $("pl-floors").innerHTML = data.floors.map(floorCard).join("") + floorCard(null)
      || '<div class="panel faint">Crea il primo piano (es. Piano terra) oppure importa le aree da Home Assistant.</div>';
    if (!document.activeElement || !document.activeElement.closest || !document.activeElement.closest("#pl-devices")) $("pl-devices").innerHTML = deviceRows();
  }

  async function load() {
    try { data = await A.api("GET", "/api/places"); render(); } catch (e) { A.toast(e.message, true); }
    clearTimeout(timer);
    timer = setTimeout(() => { if (document.getElementById("tab-places").classList.contains("on")) load(); }, 10000);
  }

  function saveDevice(row) {
    const senses = [...row.querySelectorAll("[data-sense]")].filter((c) => c.checked).map((c) => c.dataset.sense);
    call("PUT", `/api/places/devices/${encodeURIComponent(row.dataset.key)}`, { room_id: row.querySelector("[data-room]").value, senses });
  }

  function init() {
    $("pl-floor-new").addEventListener("click", () => {
      const name = (prompt("Nome del piano (es. Piano terra, Primo piano):") || "").trim();
      if (!name) return;
      const level = parseInt(prompt("Livello (0 = terra, 1 = primo, -1 = seminterrato):", String(data ? data.floors.length : 0)) || "0", 10) || 0;
      call("POST", "/api/places/floors", { name, level });
    });
    $("pl-import").addEventListener("click", async () => {
      const r = await call("POST", "/api/places/import");
      if (r) A.toast(`Importate ${r.added} stanze da Home Assistant`);
    });
    $("pl-floors").addEventListener("submit", (e) => {
      const form = e.target.closest("[data-room-add]"); if (!form) return;
      e.preventDefault();
      call("POST", "/api/places/rooms", { name: form.elements.name.value.trim(), floor_id: form.closest("[data-floor]").dataset.floor });
    });
    $("pl-floors").addEventListener("click", (e) => {
      const floorBox = e.target.closest("[data-floor]"), roomBox = e.target.closest("[data-room]");
      if (e.target.closest("[data-floor-del]") && confirm("Eliminare il piano? Le stanze restano senza piano.")) call("DELETE", `/api/places/floors/${encodeURIComponent(floorBox.dataset.floor)}`);
      if (e.target.closest("[data-floor-edit]")) {
        const floor = data.floors.find((f) => f.id === floorBox.dataset.floor);
        const name = (prompt("Nuovo nome del piano:", floor.name) || "").trim();
        if (name) call("PUT", `/api/places/floors/${encodeURIComponent(floor.id)}`, { name, level: floor.level });
      }
      if (e.target.closest("[data-room-del]") && confirm("Eliminare la stanza?")) call("DELETE", `/api/places/rooms/${encodeURIComponent(roomBox.dataset.room)}`);
      if (e.target.closest("[data-room-edit]")) {
        const room = data.rooms.find((r) => r.id === roomBox.dataset.room);
        const name = (prompt("Nuovo nome della stanza:", room.name) || "").trim();
        if (name) call("PUT", `/api/places/rooms/${encodeURIComponent(room.id)}`, { ...room, name });
      }
    });
    $("pl-devices").addEventListener("change", (e) => { const row = e.target.closest("[data-key]"); if (row) saveDevice(row); });
  }

  A.tab("places", { title: "Piani e stanze", init, load });
})();
