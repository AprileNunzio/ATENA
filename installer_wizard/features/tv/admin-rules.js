(() => {
  const A = window.AtenaAdmin, { $, fmt } = A;
  const TAG = "tv";

  function describe(a) {
    const t = a.triggers[0] || {}, act = (a.actions || []).find((x) => x.type === "tv") || {};
    const when = t.type === "time" ? `alle ${t.at}` : t.person ? `quando arriva ${t.person}` : "quando arriva qualcuno";
    const morning = (a.conditions || []).some((c) => c.type === "time") ? " (al mattino)" : "";
    return `${when}${morning} → ${act.channel} su ${act.target || "display"}`;
  }

  async function load() {
    let d;
    try { d = await A.api("GET", "/api/automations"); } catch (e) { $("tv-rules").innerHTML = `<div class="faint">${fmt.esc(e.message)}</div>`; return; }
    const rows = d.automations.filter((a) => (a.tags || []).includes(TAG));
    $("tv-rules").innerHTML = rows.map((a) => `<div class="tv-list" data-aid="${fmt.esc(a.id)}"><div><b>${fmt.esc(a.name)}</b><div class="faint">${fmt.esc(describe(a))}</div></div>
      <div class="actions"><button type="button" class="btn sm danger" data-del>✕</button></div></div>`).join("") || '<div class="muted-note">Nessuna regola.</div>';
  }

  function build() {
    const when = $("tv-when").value, person = $("tv-person").value.trim(), channel = $("tv-channel").value.trim(), target = $("tv-rtarget").value || "display";
    if (!channel) throw new Error("Scegli il canale");
    const action = { type: "tv", channel, target };
    if (when === "time") {
      return { name: `TV: ${channel} alle ${$("tv-at").value}`, triggers: [{ type: "time", at: $("tv-at").value }], actions: [action], tags: [TAG] };
    }
    const trigger = { type: "presence", event: "person_arrived", person };
    if (when === "wake") {
      return { name: `TV al risveglio: ${channel}${person ? ` per ${person}` : ""}`, triggers: [trigger],
        conditions: [{ type: "time", after: "05:00", before: "11:00" }], cooldown: 14 * 3600, actions: [action], tags: [TAG] };
    }
    return { name: `TV all'arrivo: ${channel}${person ? ` per ${person}` : ""}`, triggers: [trigger], cooldown: 1800, actions: [action], tags: [TAG] };
  }

  function init() {
    const sync = () => { $("tv-at").style.display = $("tv-when").value === "time" ? "" : "none"; $("tv-person").style.display = $("tv-when").value === "time" ? "none" : ""; };
    $("tv-when").addEventListener("change", sync); sync();
    $("tv-rule").addEventListener("submit", async (e) => {
      e.preventDefault();
      try { await A.api("POST", "/api/automations", build()); A.toast("Regola creata"); load(); } catch (err) { A.toast(err.message, true); }
    });
    $("tv-rules").addEventListener("click", async (e) => {
      const row = e.target.closest("[data-aid]");
      if (!row || !e.target.closest("[data-del]") || !confirm("Eliminare questa regola?")) return;
      try { await A.api("DELETE", `/api/automations/${encodeURIComponent(row.dataset.aid)}`); load(); } catch (err) { A.toast(err.message, true); }
    });
  }

  A.tvRules = { init, load };
})();
