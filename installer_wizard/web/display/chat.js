(() => {
  const D = window.AtenaDisplay, { $ } = D;

  function thinking(on) {
    const { avatar } = D;
    if (!avatar) return;
    avatar.setTint(on ? "#b36bff" : D.tint || "#29e0ff");
    if (avatar.face) avatar.face.thinking = on;
  }

  D.greetWake = async () => {
    if (D.busy) return;
    D.busy = true; D.lastInteraction = Date.now();
    try {
      const d = await fetch("/api/assistant/wake", { method: "POST" }).then((r) => r.json());
      parseActions(d);
      if (D.mode !== "face") D.setMode("face");
      D.Mood.joy();
      $("you").textContent = "";
      D.typeInto($("say"), d.reply);
      D.lastVoice = true;
      D.speak(d.reply);
    } catch (err) {
      D.Ear.followup(8);
    } finally {
      D.busy = false; D.lastInteraction = Date.now();
    }
  };

  function enrollUi(d) {
    if (!d.ui || d.ui.mode !== "enroll") return false;
    D.setMode("face");
    D.typeInto($("say"), d.reply);
    D.lastVoice = false;
    D.speak(d.reply);
    D.Enroll.start(d.ui);
    return true;
  }

  function parseActions(d) {
    if (!d || !d.reply) return;
    const tags = [];
    d.reply = d.reply.replace(/\[AZIONE:\s*([^\]]+)\]/gi, (match, action) => {
      tags.push(action.trim());
      return "";
    }).trim();
    if (tags.length && D.avatar && D.avatar.express) tags.forEach((tag) => D.avatar.express(tag.toLowerCase(), 2.2));
  }

  const ACTION_TAG = /\[AZIONE:[^\]]*\]?/gi;
  const SENTENCE = /^([\s\S]*?(?:[.!?…:;](?=\s)|\n))(\s*)/;

  function cleanLive(text) {
    return text.replace(ACTION_TAG, "").replace(/[ \t]+/g, " ").replace(/\n{2,}/g, "\n").trimStart();
  }

  async function askStream(text, lang, heard) {
    const r = await fetch("/api/assistant/chat/stream", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, lang, ...heard }) });
    if (!r.ok || !r.body) return null;
    const reader = r.body.getReader(), decoder = new TextDecoder();
    let buffer = "", said = "", cut = 0, code = false, voice = null, final = null;
    const speakReady = () => {
      if (code) return;
      let pending = said.slice(cut);
      const fence = pending.indexOf("```");
      if (fence >= 0) { pending = pending.slice(0, fence); code = true; }
      let m;
      while (pending && (m = SENTENCE.exec(pending)) && m[0].length) {
        voice.add(m[1]);
        cut += m[0].length;
        pending = pending.slice(m[0].length);
      }
      if (code && pending.trim()) { voice.add(pending); cut += pending.length; }
    };
    while (!final) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let split;
      while ((split = buffer.indexOf("\n\n")) >= 0) {
        const line = buffer.slice(0, split).trim();
        buffer = buffer.slice(split + 2);
        if (!line.startsWith("data: ")) continue;
        const ev = JSON.parse(line.slice(6));
        if (ev.type === "token") {
          if (!voice) { voice = D.speakStream(lang); D.setMode("face"); }
          said = cleanLive(said + ev.t);
          $("say").textContent = said;
          speakReady();
        } else if (ev.type === "error") {
          throw new Error(ev.detail || "Errore");
        } else if (ev.type === "done") {
          final = ev;
        }
      }
    }
    if (!final) throw new Error("Risposta interrotta");
    if (voice) {
      parseActions(final);
      const reply = final.reply || "", flat = cleanLive(reply), prefix = said.slice(0, cut);
      if (code || prefix.startsWith(flat)) {
        voice.close(reply);
      } else if (flat.startsWith(prefix)) {
        voice.add(flat.slice(cut));
        voice.close(reply);
      } else if (!cut) {
        voice.add(flat);
        voice.close(reply);
      } else {
        await voice.close(reply);
        D.speak(reply, final.lang);
      }
    }
    return { data: final, spoken: Boolean(voice) };
  }

  function show(text, d, spoken = false) {
    parseActions(d);
    $("you").textContent = `« ${text} »`;
    if (enrollUi(d)) return;
    const ui = d.ui || { mode: "face" };
    if (ui.mode === "focus") { D.renderStage(ui); D.typeInto($("focus-say"), d.reply); }
    D.personalUi = ui.mode === "focus" && ui.personal ? { at: Date.now() } : null;
    D.setPresence(ui.presence || "normal");
    D.setMode(ui.mode);
    if (ui.camera && D.setCamera) D.setCamera(ui.camera === "on");
    if (spoken) $("say").textContent = d.reply;
    else { D.typeInto($("say"), d.reply); D.speak(d.reply, d.lang); }
    if (ui.mode === "face" || ui.mode === "focus") setTimeout(() => D.refreshBrain(true), 1500);
  }

  async function predict(text) {
    const pred = await fetch(`/api/assistant/predict?q=${encodeURIComponent(text)}`).then((r) => r.json()).catch(() => null);
    if (pred && pred.skeleton && pred.skeleton.mode === "focus") { D.renderSkeleton(pred.skeleton); D.setMode("focus"); }
    else if (pred && pred.intent === "brain") D.setMode("brain");
  }

  D.ask = async (text, lang, heard = {}) => {
    D.busy = true; D.lastInteraction = Date.now();
    thinking(true);
    if (!heard.followup) {
      $("you").textContent = `« ${text} »`;
      $("say").textContent = "…";
    }
    try {
      if (!heard.followup) await predict(text);
      const streamed = await askStream(text, lang, heard);
      if (streamed) {
        if (streamed.data.ignored) { D.lastVoice = false; D.Ear.followup(12); return; }
        show(text, streamed.data, streamed.spoken);
        return;
      }
      const r = await fetch("/api/assistant/chat", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, lang, ...heard }) });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "Errore");
      if (d.ignored) { D.lastVoice = false; D.Ear.followup(12); return; }
      show(text, d);
    } catch (err) {
      D.setMode("face");
      $("say").textContent = `⚠ ${err.message}`;
      if (D.avatar && D.avatar.express) D.avatar.express("sad", 2.6);
    } finally {
      D.busy = false; D.lastInteraction = Date.now();
      thinking(false);
    }
  };

  D.startChat = () => {
    $("in").addEventListener("input", () => D.pingActivity(false));
    $("in").addEventListener("keydown", (e) => {
      if (e.key !== "Enter") return;
      const text = $("in").value.trim(); if (!text || D.busy) return;
      $("in").value = ""; D.ask(text);
    });
    if (!D.local) {
      fetch("/api/auth/me", { credentials: "include" }).then((r) => {
        if (!r.ok) $("note").textContent = "Accesso remoto in sola visione — per parlare con Atena accedi al pannello :8080";
      }).catch(() => {});
    }
  };
})();
