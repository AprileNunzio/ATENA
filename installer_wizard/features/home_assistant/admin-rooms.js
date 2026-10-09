(() => {
  const A = window.AtenaAdmin, { $, fmt } = A;
  const ICON = { light: "💡", switch: "🔌", fan: "🌀", cover: "🪟", climate: "🌡", media_player: "📺", scene: "🎬", lock: "🔒", vacuum: "🧹", script: "▶️" };
  const SHOWN = ["light", "switch", "fan", "cover", "climate", "media_player", "scene", "lock", "vacuum"];
  const ON = new Set(["on", "open", "opening", "playing", "heat", "cool", "auto", "heat_cool", "unlocked", "cleaning"]);
  const PER_ROOM = 8;
  let floor = "", data = null, home = null;

  function controls(roomId) {
    const list = data.entities.filter((e) => e.area_id === roomId && e.controllable && SHOWN.includes(e.domain));
    list.sort((a, b) => SHOWN.indexOf(a.domain) - SHOWN.indexOf(b.domain) || a.name.localeCompare(b.name));
    const chips = list.slice(0, PER_ROOM).map((e) => {
      const on = ON.has(e.state), off = e.state === "unavailable";
      let extra = "";
      if (e.domain === "climate" && e.attrs.temperature != null) extra = `<span class="hm-dv-v">${e.attrs.current_temperature ?? "?"}→${e.attrs.temperature}°</span><button type="button" data-temp="-0.5" data-eid="${fmt.esc(e.entity_id)}">−</button><button type="button" data-temp="0.5" data-eid="${fmt.esc(e.entity_id)}">+</button>`;
      if (e.domain === "cover" && e.attrs.current_position != null) extra = `<span class="hm-dv-v">${e.attrs.current_position}%</span>`;
      if (e.domain === "light" && on && e.attrs.brightness != null) extra = `<span class="hm-dv-v">${Math.round(e.attrs.brightness / 2.55)}%</span>`;
      return `<div class="hm-dv ${on ? "on" : ""} ${off ? "na" : ""}" data-eid="${fmt.esc(e.entity_id)}" data-domain="${e.domain}" title="${fmt.esc(e.name)} · ${fmt.esc(e.state)}">
        <button type="button" class="hm-dv-main" data-act="1"><span class="hm-dv-ic">${ICON[e.domain] || "•"}</span><span class="hm-dv-nm">${fmt.esc(e.name)}</span></button>${extra}</div>`;
    }).join("");
    const more = list.length > PER_ROOM ? `<span class="faint" style="font-size:11px">+${list.length - PER_ROOM}</span>` : "";
    return chips ? `<div class="hm-dvs">${chips}${more}</div>` : "";
  }

  function room(r) {
    return `<div class="room ${r.occupied ? "occ" : ""}">
      <div class="nm"><span class="dot ${r.occupied ? "ok" : r.has_sensors ? "idle" : ""}"></span>${fmt.esc(r.name)}</div>
      <div class="fl">${fmt.esc(r.floor || "")}${r.devices ? ` · ${r.devices} dispositivi` : ""}</div>
      <div class="lb">${fmt.esc(r.label)}</div>
      <div class="mt">${r.temperature != null ? `<span>🌡 ${r.temperature} °C</span>` : ""}${r.humidity != null ? `<span>💧 ${Math.round(r.humidity)}%</span>` : ""}
        ${r.lights_on ? `<span>💡 ${r.lights_on} accese</span>` : ""}${r.open.length ? `<span style="color:var(--amber)">🚪 ${fmt.esc(r.open.join(", "))}</span>` : ""}</div>
      ${data ? controls(r.area_id) : ""}
      <input class="x-expert" data-alias="area:${fmt.esc(r.area_id)}" value="${fmt.esc(r.aliases.join(", "))}" placeholder="Altri nomi${r.ha_aliases.length ? " (HA: " + fmt.esc(r.ha_aliases.join(", ")) + ")" : ""}"></div>`;
  }

  function render(h, entities) {
    home = h; if (entities) data = entities;
    const floors = data ? data.floors.slice().sort((a, b) => (a.level ?? 0) - (b.level ?? 0)) : [];
    $("hm-floors").innerHTML = floors.length > 1 ? `<button type="button" data-floor="" class="${floor ? "" : "on"}">Tutti</button>` + floors.map((f) => `<button type="button" data-floor="${fmt.esc(f.floor_id)}" class="${floor === f.floor_id ? "on" : ""}">${fmt.esc(f.name)}</button>`).join("") : "";
    const floorOf = (r) => (data && (data.areas.find((a) => a.area_id === r.area_id) || {}).floor_id) || "";
    const rooms = h.rooms.filter((r) => !floor || floorOf(r) === floor);
    $("hm-rooms").innerHTML = rooms.map(room).join("") || '<div class="faint">Nessuna stanza: assegna le aree ai dispositivi in Home Assistant.</div>';
  }

  async function send(eid, service, body = {}) {
    try {
      await A.api("POST", "/api/home/control", { entity_id: eid, service, ...body });
      return true;
    } catch (e) {
      if (/conferma/.test(e.message) && confirm(`${e.message}. Procedere?`)) return send(eid, service, { ...body, confirm: true });
      A.toast(e.message, true); return false;
    }
  }

  function serviceFor(e) {
    const svc = data.services[e.domain] || [], on = ON.has(e.state);
    if (e.domain === "scene") return "turn_on";
    if (e.domain === "cover") return on ? "close_cover" : "open_cover";
    if (e.domain === "lock") return e.state === "locked" ? "unlock" : "lock";
    if (e.domain === "vacuum") return on ? "return_to_base" : "start";
    if (svc.includes("toggle")) return "toggle";
    return on ? "turn_off" : "turn_on";
  }

  async function act(ev) {
    const temp = ev.target.closest("[data-temp]");
    const box = ev.target.closest(".hm-dv");
    if (!box || !data) return;
    const e = data.entities.find((x) => x.entity_id === box.dataset.eid);
    if (!e) return;
    box.classList.add("busy");
    const ok = temp ? await send(e.entity_id, "set_temperature", { data: { temperature: Math.round(((e.attrs.temperature || 20) + Number(temp.dataset.temp)) * 2) / 2 } })
      : ev.target.closest("[data-act]") ? await send(e.entity_id, serviceFor(e)) : false;
    box.classList.remove("busy");
    if (ok) setTimeout(() => A.homeReload && A.homeReload(), 500);
  }

  function init() {
    $("hm-rooms").addEventListener("click", act);
    $("hm-floors").addEventListener("click", (e) => { const b = e.target.closest("[data-floor]"); if (b && home) { floor = b.dataset.floor; render(home); } });
  }

  A.homeRooms = { init, render };
})();
