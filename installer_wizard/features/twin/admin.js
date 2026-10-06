(() => {
  const A = window.AtenaAdmin, { $, fmt } = A;
  let data = null, bus = null;
  const when = (t) => new Date(t * 1000).toLocaleString(document.documentElement.lang || undefined, { dateStyle: "short", timeStyle: "medium" });
  const fail = (err) => A.toast(A.t(err.message), true);

  function conflictText(c) {
    return A.t(`twin.rule.${c.rule}.text`, { culprits: c.culprits.join(", ") || "—", subjects: c.subjects.join(", ") || "—" });
  }

  function verdict(v) {
    const dropped = v.dropped.map((d) => `${fmt.esc(d.service)} → ${fmt.esc(d.entity)}`).join(", ");
    return `<div class="tw-item ${v.blocked || v.dropped.length ? "block" : "warn"}">
      <div><b>${fmt.esc(v.text || v.source || "")}</b> <span class="faint">${v.at ? fmt.esc(when(v.at)) : ""}</span></div>
      ${v.conflicts.map((c) => `<div class="faint">${c.severity === "block" ? "⛔" : "⚠️"} ${fmt.esc(conflictText(c))}</div>`).join("")}
      ${dropped ? `<div>${fmt.esc(A.t("twin.dropped"))}: ${dropped}</div>` : ""}
      ${!v.conflicts.length ? `<div class="faint">${fmt.esc(A.t("twin.clean"))}</div>` : ""}</div>`;
  }

  function render() {
    $("tw-mode").textContent = A.t("twin.mode_now", { mode: A.t(`twin.mode.${data.mode}`) });
    $("tw-rules").innerHTML = data.available.map((r) => `<label class="tw-item"><span class="switch">
      <input type="checkbox" data-rule="${fmt.esc(r)}" ${data.rules[r] ? "checked" : ""}><b>${fmt.esc(A.t(`twin.rule.${r}.name`))}</b></span>
      <span class="faint">${fmt.esc(A.t(`twin.rule.${r}.help`))}</span></label>`).join("");
    $("tw-history").innerHTML = data.history.map(verdict).join("") || `<div class="faint">${fmt.esc(A.t("twin.no_history"))}</div>`;
  }

  async function load() {
    try { data = await A.api("GET", "/api/twin"); render(); } catch (err) { fail(err); }
    if (!bus) bus = window.Atena.subscribeBus("twin.verdict", (env) => { if (data) { data.history = [env.payload, ...data.history].slice(0, 50); render(); } });
  }

  function init() {
    $("tw-rules").addEventListener("change", async (e) => {
      const box = e.target.closest("[data-rule]"); if (!box) return;
      try { data.rules = (await A.api("PUT", "/api/twin/rules", { [box.dataset.rule]: box.checked })).rules; A.toast(A.t("twin.saved")); }
      catch (err) { box.checked = !box.checked; fail(err); }
    });
    $("tw-sim").addEventListener("submit", async (e) => {
      e.preventDefault();
      const calls = $("tw-plan").value.split("\n").map((l) => l.trim().split(/\s+/)).filter((p) => p.length >= 2)
        .map(([service, ...entities]) => ({ service, entity_ids: entities }));
      try { $("tw-result").innerHTML = verdict({ ...(await A.api("POST", "/api/twin/simulate", { calls })), text: A.t("twin.simulation") }); }
      catch (err) { fail(err); }
    });
    window.addEventListener("atena-i18n", () => { if (data && A.isOn("twin")) render(); });
  }

  A.tab("twin", { title: "Gemello digitale", init, load, leave() { if (bus) { bus.close(); bus = null; } } });
})();
