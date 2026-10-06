(() => {
  const A = window.AtenaAdmin, { $, fmt } = A;
  const STATUS = { new: "da decidere", snoozed: "rimandata", accepted: "automatizzata", rejected: "rifiutata" };
  const KIND = { time: "⏰", sun: "🌅", arrival: "🧍" };
  const when = (t) => (t ? new Date(t * 1000).toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" }) : "mai");
  let timer = null;

  function render(d) {
    $("hb-status").textContent = `${d.enabled ? "Attive" : "Disattivate"} · ${d.events} azioni osservate · ultima analisi ${when(d.mined)}`
      + ` · proposta quando è regolare almeno ${Math.round(d.threshold * 10)} volte su 10` + (d.asking ? " · in attesa della sua risposta a voce" : "");
    $("hb-list").innerHTML = d.suggestions.map((s) => `<div class="hb-item ${s.status}" data-id="${fmt.esc(s.id)}">
      <div><b>${KIND[s.kind] || ""} ${fmt.esc(s.text.charAt(0).toUpperCase() + s.text.slice(1))}</b>
        <span class="badge ${s.status === "accepted" ? "ok" : ""}">${STATUS[s.status] || s.status}</span>
        <div class="faint">${s.support} volte su ${s.observed} · ${fmt.esc(s.entity)} → ${fmt.esc(s.state)}</div>
        <div class="hb-bar"><i style="width:${Math.round(s.confidence * 100)}%"></i></div></div>
      <div class="actions">${s.status === "accepted" ? "" : `<button class="btn sm primary" data-v="accept">Automatizza</button>
        <button class="btn sm" data-v="snooze">Più tardi</button>${s.status !== "rejected" ? '<button class="btn sm danger" data-v="reject">No</button>' : ""}`}</div></div>`).join("")
      || '<div class="faint">Ancora nessuna abitudine riconosciuta: servono almeno 5 giorni di uso della casa con Home Assistant collegato.</div>';
    $("hb-odd").innerHTML = d.anomalies.map((a) => `<div class="hb-item"><div>${fmt.esc(a.text)}<div class="faint">${when(a.at)}</div></div></div>`).join("")
      || '<div class="faint">Nessuna.</div>';
  }

  function context(ctx) {
    const [day, slot, light, occupancy] = ctx.split("|");
    return [A.t(`feedback.day.${day}`), A.t("feedback.slot", { from: slot * 3, to: slot * 3 + 3 }), A.t(`feedback.light.${light}`),
      A.t(`feedback.occupancy.${occupancy}`)].join(" · ");
  }

  function renderFeedback(d) {
    $("hb-feedback").innerHTML = d.items.map((r) => `<div class="hb-item" data-key="${fmt.esc(r.key)}">
      <div><b>${fmt.esc(r.entity)} → ${fmt.esc(r.target)}</b> <span class="badge ${r.suppressed ? "down" : r.acceptance >= 0.7 ? "ok" : ""}">${fmt.esc(A.t(r.suppressed ? "feedback.suppressed" : `feedback.kind.${r.kind}`))}</span>
        <div class="faint">${fmt.esc(context(r.context))} · ${fmt.esc(A.t("feedback.counts", { ok: r.ok, undo: r.undo }))}</div>
        <div class="hb-bar"><i style="width:${Math.round(r.acceptance * 100)}%"></i></div></div>
      <div class="actions"><button class="btn sm" data-fb-reset>${fmt.esc(A.t("feedback.reset"))}</button></div></div>`).join("")
      || `<div class="faint">${fmt.esc(A.t("feedback.empty"))}</div>`;
  }

  async function loadFeedback() { try { renderFeedback(await A.api("GET", "/api/habits/feedback")); } catch (e) { A.toast(A.t(e.message), true); } }

  async function load() { try { render(await A.api("GET", "/api/habits")); } catch (e) { $("hb-status").textContent = e.message; } loadFeedback(); }

  function init() {
    $("hb-feedback").addEventListener("click", async (e) => {
      const item = e.target.closest("[data-key]"); if (!item || !e.target.closest("[data-fb-reset]")) return;
      await A.api("DELETE", `/api/habits/feedback?key=${encodeURIComponent(item.dataset.key)}`).catch((err) => A.toast(A.t(err.message), true));
      loadFeedback();
    });
    $("hb-fb-reset").addEventListener("click", async () => {
      if (!confirm(A.t("feedback.confirm_reset"))) return;
      await A.api("DELETE", "/api/habits/feedback").catch((err) => A.toast(A.t(err.message), true));
      loadFeedback();
    });
    $("hb-analyse").addEventListener("click", async () => { const r = await A.api("POST", "/api/habits/analyse"); A.toast(`${r.found} abitudini trovate`); load(); });
    $("hb-list").addEventListener("click", async (e) => {
      const b = e.target.closest("[data-v]"), item = e.target.closest("[data-id]"); if (!b || !item) return;
      try { const r = await A.api("POST", `/api/habits/${encodeURIComponent(item.dataset.id)}`, { verdict: b.dataset.v }); A.toast(r.message); load(); }
      catch (err) { A.toast(err.message, true); }
    });
  }

  A.tab("habits", {
    title: "Abitudini", init,
    load() { load(); clearInterval(timer); timer = setInterval(() => { if (A.isOn("habits")) load(); }, 20000); },
    leave() { clearInterval(timer); },
  });
})();
