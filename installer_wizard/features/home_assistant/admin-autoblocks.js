(() => {
  const A = window.AtenaAdmin;
  const only = (obj, keys) => Object.keys(obj).every((k) => keys.includes(k));
  const one = (v) => (typeof v === "string" ? v : Array.isArray(v) && v.length === 1 && typeof v[0] === "string" ? v[0] : null);
  const minutesOf = (d) => {
    if (d == null) return "";
    if (typeof d === "object" && only(d, ["hours", "minutes", "seconds"])) return (Number(d.hours || 0) * 60 + Number(d.minutes || 0) + Number(d.seconds || 0) / 60) || "";
    if (typeof d === "string" && /^-?\d{1,2}:\d{2}(:\d{2})?$/.test(d)) { const neg = d.startsWith("-"), [h, m] = d.replace("-", "").split(":").map(Number); return (neg ? -1 : 1) * (h * 60 + m); }
    return null;
  };
  const offset = (min) => { const n = Number(min) || 0, s = n < 0 ? "-" : "", a = Math.abs(n); return `${s}${String(Math.floor(a / 60)).padStart(2, "0")}:${String(a % 60).padStart(2, "0")}:00`; };
  const hhmm = (t) => (typeof t === "string" && /^\d{1,2}:\d{2}(:\d{2})?$/.test(t) ? t.slice(0, 5) : null);

  const TRIGGERS = {
    state: { label: "Un dispositivo cambia stato", fields: [["entity", "Dispositivo", "entity"], ["to", "Diventa (vuoto = qualsiasi cambio)", "state"], ["for_min", "Da almeno (minuti)", "number"]],
      read(b) { const e = one(b.entity_id), m = minutesOf(b.for); if (!e || m === null || !only(b, ["trigger", "platform", "entity_id", "to", "from", "for", "id"]) || b.from !== undefined) return null; return { entity: e, to: b.to ?? "", for_min: m }; },
      write(v) { const b = { trigger: "state", entity_id: v.entity }; if (v.to !== "") b.to = v.to; if (Number(v.for_min) > 0) b.for = { minutes: Number(v.for_min) }; return b; } },
    numeric_state: { label: "Un valore supera una soglia", fields: [["entity", "Sensore", "entity"], ["above", "Sopra", "number"], ["below", "Sotto", "number"]],
      read(b) { const e = one(b.entity_id); if (!e || !only(b, ["trigger", "platform", "entity_id", "above", "below", "id"])) return null; return { entity: e, above: b.above ?? "", below: b.below ?? "" }; },
      write(v) { const b = { trigger: "numeric_state", entity_id: v.entity }; if (v.above !== "") b.above = Number(v.above); if (v.below !== "") b.below = Number(v.below); return b; } },
    time: { label: "A un orario", fields: [["at", "Orario", "time"]],
      read(b) { const t = hhmm(b.at); return t && only(b, ["trigger", "platform", "at", "id"]) ? { at: t } : null; },
      write(v) { return { trigger: "time", at: `${v.at || "07:00"}:00` }; } },
    sun: { label: "Alba o tramonto", fields: [["event", "Quando", "sun"], ["offset_min", "Spostamento (minuti, anche negativo)", "number"]],
      read(b) { const m = b.offset === undefined ? 0 : minutesOf(b.offset); return m === null || !only(b, ["trigger", "platform", "event", "offset", "id"]) ? null : { event: b.event || "sunset", offset_min: m || "" }; },
      write(v) { const b = { trigger: "sun", event: v.event || "sunset" }; if (Number(v.offset_min)) b.offset = offset(v.offset_min); return b; } },
    homeassistant: { label: "Home Assistant si avvia", fields: [],
      read(b) { return b.event === "start" && only(b, ["trigger", "platform", "event", "id"]) ? {} : null; },
      write() { return { trigger: "homeassistant", event: "start" }; } },
  };

  const CONDITIONS = {
    state: { label: "Un dispositivo è in uno stato", fields: [["entity", "Dispositivo", "entity"], ["state", "Stato", "state"]],
      read(b) { const e = one(b.entity_id); return e && typeof b.state === "string" && only(b, ["condition", "entity_id", "state"]) ? { entity: e, state: b.state } : null; },
      write(v) { return { condition: "state", entity_id: v.entity, state: v.state || "on" }; } },
    time: { label: "In una fascia oraria o in certi giorni", fields: [["after", "Dopo le", "time"], ["before", "Prima delle", "time"], ["weekday", "Giorni", "days"]],
      read(b) { if (!only(b, ["condition", "after", "before", "weekday"])) return null; const a = b.after ? hhmm(b.after) : "", z = b.before ? hhmm(b.before) : ""; if (a === null || z === null) return null; return { after: a, before: z, weekday: [].concat(b.weekday || []) }; },
      write(v) { const b = { condition: "time" }; if (v.after) b.after = `${v.after}:00`; if (v.before) b.before = `${v.before}:00`; if (v.weekday.length) b.weekday = v.weekday; return b; } },
    sun: { label: "Di giorno o di notte", fields: [["part", "Momento", "daypart"]],
      read(b) { if (!only(b, ["condition", "after", "before"])) return null; if (b.after === "sunset" && b.before === "sunrise") return { part: "night" }; if (b.after === "sunrise" && b.before === "sunset") return { part: "day" }; return null; },
      write(v) { return v.part === "day" ? { condition: "sun", after: "sunrise", before: "sunset" } : { condition: "sun", after: "sunset", before: "sunrise" }; } },
  };

  const ACTIONS = {
    device: { label: "Comanda un dispositivo", fields: [["entity", "Dispositivi", "controls"], ["service", "Cosa fare", "service"], ["brightness_pct", "Luminosità % (solo luci)", "number"]],
      read(b) {
        const call = b.action || b.service; if (typeof call !== "string" || call.startsWith("notify.") || !only(b, ["action", "service", "target", "data", "entity_id"])) return null;
        const raw = (b.target || {}).entity_id ?? b.entity_id, list = [].concat(raw || []), data = b.data || {};
        if (!list.length || !list.every((x) => typeof x === "string" && !x.includes("{{")) || new Set(list.map((x) => x.split(".")[0])).size > 1) return null;
        if ((b.target && !only(b.target, ["entity_id"])) || !only(data, ["brightness_pct"])) return null;
        return { entity: list, service: call.split(".")[1], brightness_pct: data.brightness_pct ?? "" };
      },
      write(v) { const list = [].concat(v.entity || []).filter(Boolean), domain = (list[0] || "").split(".")[0]; const b = { action: `${domain}.${v.service || "turn_on"}`, target: { entity_id: list.length === 1 ? list[0] : list } }; if (domain === "light" && v.service === "turn_on" && v.brightness_pct !== "") b.data = { brightness_pct: Number(v.brightness_pct) }; return b; } },
    delay: { label: "Aspetta", fields: [["minutes", "Minuti", "number"]],
      read(b) { const m = minutesOf(b.delay); return m === null || m === "" || !only(b, ["delay"]) ? null : { minutes: m }; },
      write(v) { return { delay: { minutes: Number(v.minutes) || 1 } }; } },
    notify: { label: "Manda una notifica", fields: [["message", "Messaggio", "text"]],
      read(b) { const call = b.action || b.service; return typeof call === "string" && call.startsWith("notify.") && only(b, ["action", "service", "data"]) && only(b.data || {}, ["message"]) ? { message: (b.data || {}).message || "" } : null; },
      write(v) { return { action: "notify.notify", data: { message: v.message || "" } }; } },
  };

  const KINDS = { triggers: TRIGGERS, conditions: CONDITIONS, actions: ACTIONS };

  function parse(section, block) {
    const table = KINDS[section];
    if (block && typeof block === "object") {
      for (const [type, spec] of Object.entries(table)) {
        const kindKey = section === "triggers" ? (block.trigger || block.platform) : section === "conditions" ? block.condition : null;
        if (section !== "actions" && kindKey !== type) continue;
        const v = spec.read(block);
        if (v) return { type, v };
      }
    }
    return { type: "raw", raw: block };
  }

  function build(section, item) {
    return item.type === "raw" ? item.raw : KINDS[section][item.type].write(item.v);
  }

  A.homeBlocks = { KINDS, parse, build };
})();
