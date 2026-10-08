(function (J) {
  "use strict";
  const { damp } = J;
  const C = (J.Char = J.Char || {});
  const WET = { drizzle: 0.4, rain: 0.75, storm: 1 };
  const FIDGETS = [
    ["stiracchia", 1, 2], ["capelli", 1, 1], ["orologio", 1, 1], ["mani_fianchi", 1, 2, 6], ["braccia_conserte", 1, 2, 8],
    ["stroll", 3, 0], ["guarda", 2, 0],
  ];
  const BEATS = ["spiega_a", "spiega_b", "spiega_c", "spiega_b"];

  function pick(list) {
    const total = list.reduce((s, f) => s + f[1], 0);
    let r = Math.random() * total;
    for (const f of list) { r -= f[1]; if (r <= 0) return f; }
    return list[0];
  }

  class Life {
    constructor(avatar) {
      this.a = avatar;
      this.quiet = 0; this.nextFidget = 7; this.nextBeat = 0; this.nextShiver = 0;
      this.weather = ""; this.stroll = null; this.walking = false;
      this.danceUntil = 0; this.forcedDance = false; this.mood = null; this.moodUntil = 0;
      this.wasThinking = false; this.wasListening = false;
    }

    setWeather(icon) {
      this.weather = String(icon || "");
      this.a.rain.set(WET[this.weather] || 0);
      this.umbrella(!!WET[this.weather]);
    }

    umbrella(on) {
      this.a.umbrella.set(on);
      if (on && !this.a.gestures.active("ombrello")) this.a.gestures.play("ombrello", { persist: true });
      if (!on) this.a.gestures.stop("ombrello");
    }

    dance(on) { this.forcedDance = !!on; }
    setMood(name, seconds) { this.mood = name; this.moodUntil = performance.now() + seconds * 1000; }
    walkTo(x) { this.stroll = { to: Math.max(-0.9, Math.min(0.9, x)) }; }

    fidget(name) {
      const f = FIDGETS.find((x) => x[0] === name) || pick(FIDGETS.filter((x) => !(this.a.umbrella.on && x[2] === 2)));
      if (f[0] === "stroll") { const x = this.a.facing.position.x; this.walkTo((x > 0 ? -1 : 1) * (0.3 + Math.random() * 0.55)); return; }
      if (f[0] === "guarda") { this.a.gaze.set(Math.random() < 0.5 ? 0.1 : 0.9, 0.35 + Math.random() * 0.3); return; }
      this.a.gestures.play(f[0], { hold: f[3] ? f[3] + Math.random() * 3 : 0 });
    }

    _stroll(dt, busy) {
      const f = this.a.facing;
      if (!this.stroll && busy && Math.abs(f.position.x) > 0.12) this.stroll = { to: 0 };
      const s = this.stroll;
      this.walking = false;
      if (!s) { f.rotation.y = damp(f.rotation.y, 0, 4, dt); return; }
      if (busy) s.to = 0;
      const dx = s.to - f.position.x;
      if (Math.abs(dx) < 0.02) {
        f.rotation.y = damp(f.rotation.y, 0, 4.5, dt);
        if (Math.abs(f.rotation.y) < 0.04) this.stroll = null;
        else this.walking = Math.abs(f.rotation.y) > 0.5;
        return;
      }
      const yaw = Math.sign(dx) * Math.PI * 0.5;
      f.rotation.y = damp(f.rotation.y, yaw, 4.5, dt);
      this.walking = true;
      if (Math.abs(f.rotation.y - yaw) < 0.5) f.position.x += Math.sign(dx) * Math.min(Math.abs(dx), 0.42 * dt);
    }

    update(t, dt, st) {
      const a = this.a, g = a.gestures, m = a.motion;
      const busy = st.speaking || st.listening || st.thinking;
      this.quiet = busy ? 0 : this.quiet + dt;
      if (st.thinking !== this.wasThinking) {
        this.wasThinking = st.thinking;
        if (st.thinking) g.play("pensa"); else g.stop("pensa");
      }
      if (st.listening !== this.wasListening) {
        this.wasListening = st.listening;
        if (st.listening) g.play("ascolto"); else g.stop("ascolto");
      }
      if (st.groove > 0.3) this.danceUntil = t + 2;
      const dancing = this.forcedDance || t < this.danceUntil;
      if (this.mood && performance.now() > this.moodUntil) this.mood = null;
      this._stroll(dt, busy || dancing);
      if (dancing) m.setBase("dance");
      else if (this.walking) m.setBase("walk", 0.9);
      else m.setBase(this.mood || "idle");
      if (st.speaking && !dancing && t > this.nextBeat) {
        if (!g.active("pensa") && Math.random() < 0.75) g.play(BEATS[Math.floor(Math.random() * BEATS.length)]);
        this.nextBeat = t + 1.6 + Math.random() * 2.2;
      }
      if (this.weather === "snow" && !busy && t > this.nextShiver) { g.play("freddo"); this.nextShiver = t + 14 + Math.random() * 10; }
      if (!busy && !dancing && !this.stroll && this.quiet > 6 && t > this.nextFidget && !g.any()) {
        this.fidget();
        this.nextFidget = t + 8 + Math.random() * 12;
      } else if (!busy && !dancing && !this.stroll && this.quiet > 6 && t > this.nextFidget) {
        this.nextFidget = t + 3;
      }
    }
  }

  C.Life = Life;
})(window.Atena3D);
