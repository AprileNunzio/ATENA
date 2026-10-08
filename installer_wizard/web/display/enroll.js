(() => {
  const D = window.AtenaDisplay, { fmt } = D;
  const LABELS = { wake: "Dì il mio nome", command: "Dì il comando", reading: "Leggi la frase" };
  let session = null, seenRequest = "";

  function box() {
    let el = document.getElementById("enroll");
    if (!el) {
      el = document.createElement("div");
      el.id = "enroll";
      el.className = "enroll";
      document.body.appendChild(el);
      el.addEventListener("click", (e) => { if (e.target.closest("[data-stop]")) finish(true); });
    }
    return el;
  }

  function draw(note) {
    const s = session, total = s.plan.length, item = s.plan[Math.min(s.index, total - 1)];
    const pct = Math.round((s.index / total) * 100);
    box().innerHTML = `<div class="en-card"><div class="en-head">🎙 Impariamo la tua voce, ${fmt.esc(s.name)}</div>
      <div class="en-bar"><i style="width:${pct}%"></i></div>
      <div class="en-step">Passo ${Math.min(s.index + 1, total)} di ${total} · ${fmt.esc(LABELS[item.kind] || LABELS.reading)}</div>
      <div class="en-text">${fmt.esc(item.text)}</div>
      ${s.heard ? `<div class="en-note">Ho capito: «${fmt.esc(s.heard)}»</div>` : ""}
      <div class="en-note">${fmt.esc(note || "Parla con calma e con il tuo tono normale, alla distanza a cui parli di solito.")}</div>
      <button class="pill-btn" data-stop>Interrompi</button></div>`;
    box().classList.add("show");
  }

  function expect() {
    if (session && session.train) D.Ear.send({ type: "enroll_expect", kind: session.plan[session.index].kind });
  }

  function levelNote(level) {
    if (!level) return "";
    if (level.advice === "lower" || level.clipping > 0.02) return "Il microfono è un po' troppo alto: allontanati leggermente o abbassalo.";
    if (level.advice === "raise" || level.rms < 0.01) return "Ti sento piano: avvicinati un po' al microfono.";
    return "";
  }

  async function save(s) {
    const r = await fetch(`/api/people/${encodeURIComponent(s.slug)}/voice-training`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ lang: s.lang, answers: s.answers }) });
    if (!r.ok) throw new Error(`salvataggio non riuscito (${r.status})`);
    return r.json();
  }

  async function finish(stopped) {
    if (!session) return;
    D.Ear.send({ type: "enroll_stop" });
    const s = session;
    session = null;
    box().classList.remove("show");
    let text = stopped ? "Test interrotto: continuerò comunque a imparare la tua voce mentre parliamo."
      : `Perfetto, ${s.name}: da adesso ti riconosco anche dalla voce.`;
    if (s.train && s.answers.length) {
      try {
        const result = await save(s);
        if (!stopped) text = `Perfetto, ${s.name}: ho imparato la tua voce e come pronunci il mio nome. Ho capito il ${result.score}% delle frasi.`;
      } catch (err) {
        console.warn("Addestramento vocale non salvato", err);
        text = "Ho imparato la tua voce, ma non sono riuscita a salvare il dizionario: riprova più tardi.";
      }
    }
    D.typeInto(document.getElementById("say"), text);
    D.speak(text);
  }

  D.Enroll = {
    start(ui) {
      if (!D.local || session) return;
      const plan = Array.isArray(ui.plan) && ui.plan.length ? ui.plan : (ui.sentences || []).map((text) => ({ kind: "reading", text }));
      if (!plan.length) return;
      session = { slug: ui.slug, name: ui.name, lang: ui.lang || "it", train: !!ui.train, plan, index: 0, answers: [], heard: "" };
      draw();
      setTimeout(() => { if (session) { D.Ear.send({ type: "enroll_start", slug: session.slug, train: session.train }); expect(); } }, 3500);
    },
    progress(ev) {
      if (!session) return;
      if (!("heard" in ev) && session.started === undefined) { session.started = ev.count || 0; return; }
      if (!ev.ok) { draw("Non ho sentito bene: ripeti la frase un po' più vicino al microfono."); return; }
      if (session.train) {
        session.answers.push({ index: session.index, heard: ev.heard || "", level: ev.level || {} });
        session.heard = ev.heard || "";
      }
      session.index += 1;
      if (session.index >= session.plan.length) { finish(false); return; }
      draw(levelNote(ev.level));
      expect();
    },
    fromState(request) {
      if (!request || !request.id || request.id === seenRequest) return;
      seenRequest = request.id;
      if (Date.now() / 1000 - (request.at || 0) < 600) this.start(request);
    },
    unavailable() {
      session = null;
      box().classList.remove("show");
      const text = "Su questo sistema l'impronta vocale non è disponibile: continuerò a riconoscerti dal volto.";
      D.typeInto(document.getElementById("say"), text);
      D.speak(text);
    },
    get active() { return !!session; },
  };
})();
