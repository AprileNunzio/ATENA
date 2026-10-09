(() => {
  const A = window.AtenaAdmin, { $, fmt } = A;
  const HOUSEHOLD = "_casa";
  let data = null, who = HOUSEHOLD, draft = null, teams = [];

  const color = (c) => `#${/^[0-9a-f]{6}$/i.test(c || "") ? c : "29e0ff"}`;
  const crest = (t) => `<span class="sp-crest" style="--team:${color(t.color)}">${fmt.esc((t.abbr || t.name || "?").slice(0, 3))}</span>`;
  const leagueName = (code) => ((data.leagues.find((l) => l.code === code) || {}).name || code);
  const when = (iso) => new Date(iso).toLocaleString(undefined, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

  function renderPeople() {
    $("sp-people").innerHTML = data.people.map((p) => `<button type="button" class="chip ${p.slug === who ? "on" : ""}" data-who="${fmt.esc(p.slug)}">${p.slug === HOUSEHOLD ? "🏠" : "👤"} ${fmt.esc(p.name)}</button>`).join("");
  }

  function renderForm() {
    $("sp-teams").innerHTML = draft.teams.map((t, i) => `<div class="sp-team">${crest(t)}<div><b>${fmt.esc(t.name)}</b><div class="faint">${fmt.esc(leagueName(t.league))}</div></div>
      <button type="button" class="btn sm" data-drop="${i}" title="Togli">✕</button></div>`).join("") || '<div class="muted-note">Nessuna squadra: scegline una qui sotto.</div>';
    $("sp-f1").checked = draft.f1;
    $("sp-drivers").value = draft.f1_drivers.join(", ");
    document.querySelectorAll("#tab-sports [data-alert]").forEach((c) => { c.checked = draft.alerts[c.dataset.alert] !== false; });
    $("sp-voice").checked = draft.voice;
    $("sp-near").checked = draft.proximity;
  }

  function card(c) {
    if (c.match) {
      const m = c.match, label = { live: "In corso", today: "Oggi", result: "Risultato", next: "Prossima" }[c.kind] || "";
      const score = m.state === "pre" ? when(m.start) : `${m.home.score ?? 0} – ${m.away.score ?? 0}${m.state === "in" ? ` · ${m.clock}` : ""}`;
      return `<div class="sp-card ${c.kind}"><span class="badge">${fmt.esc(label)}</span><div class="sp-vs">${crest(m.home)} ${fmt.esc(m.home.short)} <b>${fmt.esc(score)}</b> ${fmt.esc(m.away.short)} ${crest(m.away)}</div><div class="faint">${fmt.esc(m.league_name)}</div></div>`;
    }
    const race = c.race || {}, s = c.session || {};
    return `<div class="sp-card"><span class="badge">🏎️ F1</span><div><b>${fmt.esc(race.name || "")}</b></div><div class="faint">${c.mode === "results" ? "Risultati" : `${fmt.esc(s.name || "")} · ${s.start ? when(s.start) : ""}`}</div></div>`;
  }

  async function preview() {
    $("sp-cards").innerHTML = '<div class="faint">Carico…</div>';
    try {
      const r = await A.api("GET", `/api/sports/preview/${encodeURIComponent(who)}`);
      $("sp-cards").innerHTML = r.cards.map(card).join("") || '<div class="muted-note">Niente da mostrare: aggiungi una squadra o la Formula 1.</div>';
    } catch (e) { $("sp-cards").innerHTML = `<div class="faint">${fmt.esc(e.message)}</div>`; }
  }

  function pick(slug) {
    who = slug;
    draft = JSON.parse(JSON.stringify(data.prefs[slug]));
    renderPeople(); renderForm(); preview();
  }

  async function loadTeams() {
    const code = $("sp-league").value;
    $("sp-team").innerHTML = '<option value="">Carico…</option>';
    try { teams = (await A.api("GET", `/api/sports/teams/${encodeURIComponent(code)}`)).teams; }
    catch (e) { teams = []; A.toast(e.message, true); }
    $("sp-team").innerHTML = '<option value="">Scegli la squadra…</option>' + teams.map((t) => `<option value="${fmt.esc(t.id)}">${fmt.esc(t.name)}</option>`).join("");
  }

  function collect() {
    draft.f1 = $("sp-f1").checked;
    draft.f1_drivers = $("sp-drivers").value.split(",").map((x) => x.trim().toUpperCase()).filter((x) => /^[A-Z]{3}$/.test(x));
    document.querySelectorAll("#tab-sports [data-alert]").forEach((c) => { draft.alerts[c.dataset.alert] = c.checked; });
    draft.voice = $("sp-voice").checked;
    draft.proximity = $("sp-near").checked;
  }

  async function save() {
    collect();
    try { data.prefs[who] = await A.api("PUT", `/api/sports/prefs/${encodeURIComponent(who)}`, draft); A.toast("Preferenze sportive salvate"); preview(); }
    catch (e) { A.toast(e.message, true); }
  }

  async function load() {
    try { data = await A.api("GET", "/api/sports"); } catch (e) { A.toast(e.message, true); return; }
    if (!$("sp-league").options.length) {
      $("sp-league").innerHTML = data.leagues.map((l) => `<option value="${l.code}">${l.flag} ${fmt.esc(l.name)}</option>`).join("");
      loadTeams();
    }
    if (!data.prefs[who]) who = HOUSEHOLD;
    $("sp-status").textContent = data.error ? `Ultimo errore della fonte: ${data.error}` : `${data.live.length} partite seguite oggi`;
    pick(who);
  }

  function init() {
    $("sp-people").addEventListener("click", (e) => { const b = e.target.closest("[data-who]"); if (b) { collect(); pick(b.dataset.who); } });
    $("sp-league").addEventListener("change", loadTeams);
    $("sp-add").addEventListener("click", () => {
      const t = teams.find((x) => x.id === $("sp-team").value);
      if (!t) { A.toast("Scegli prima una squadra", true); return; }
      collect();
      if (!draft.teams.some((x) => x.id === t.id && x.league === $("sp-league").value)) draft.teams.push({ ...t, league: $("sp-league").value });
      renderForm();
    });
    $("sp-teams").addEventListener("click", (e) => { const b = e.target.closest("[data-drop]"); if (b) { collect(); draft.teams.splice(Number(b.dataset.drop), 1); renderForm(); } });
    $("sp-save").addEventListener("click", save);
    $("sp-refresh").addEventListener("click", preview);
    $("sp-show").addEventListener("click", async () => {
      try { await A.api("POST", `/api/sports/show/${encodeURIComponent(who)}`); A.toast("Mostrato sullo schermo di Atena"); } catch (e) { A.toast(e.message, true); }
    });
  }

  A.tab("sports", { title: "Sport", init, load });
})();
