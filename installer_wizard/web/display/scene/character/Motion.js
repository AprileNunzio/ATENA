(function (J) {
  "use strict";
  const { THREE, damp } = J;
  const C = (J.Char = J.Char || {});
  const SOURCES = {
    idle: ["idle"], walk: ["walk"], run: ["run"], dance: ["sambadance", "samba", "dance"],
    agree: ["agree"], shake: ["headshake"], sad: ["sad_pose", "sad"], sneak: ["sneak_pose", "sneak"],
  };
  const ONCE = new Set(["agree", "shake"]);

  class Motion {
    constructor(root) {
      this.mixer = new THREE.AnimationMixer(root);
      this.entries = {};
      this.base = "idle";
      this.speed = {};
    }

    add(clips) {
      for (const clip of clips) {
        const n = clip.name.toLowerCase();
        const name = Object.keys(SOURCES).find((k) => SOURCES[k].some((s) => n === s || n.endsWith(s)));
        if (!name || this.entries[name]) continue;
        const action = this.mixer.clipAction(clip);
        if (ONCE.has(name)) { action.setLoop(THREE.LoopOnce, 1); action.clampWhenFinished = true; }
        else { action.play(); action.time = Math.random() * clip.duration; }
        action.setEffectiveWeight(0);
        this.entries[name] = { action, w: 0, until: 0, once: ONCE.has(name), dur: clip.duration };
      }
      return this;
    }

    has(name) { return !!this.entries[name]; }
    ready() { return this.has("idle"); }
    names() { return Object.keys(this.entries); }

    setBase(name, speed = 1) {
      this.base = this.entries[name] ? name : "idle";
      this.speed[this.base] = speed;
    }

    once(name) {
      const e = this.entries[name];
      if (!e) return false;
      e.action.reset().play();
      e.until = performance.now() + e.dur * 1000 - 250;
      return true;
    }

    update(dt) {
      const now = performance.now();
      let shot = 0;
      for (const name in this.entries) {
        const e = this.entries[name];
        if (!e.once) continue;
        e.w = damp(e.w, now < e.until ? 1 : 0, 9, dt);
        if (e.w < 0.002 && now >= e.until) { e.w = 0; e.action.stop(); }
        shot = Math.max(shot, e.w);
      }
      for (const name in this.entries) {
        const e = this.entries[name];
        if (e.once) continue;
        e.w = damp(e.w, name === this.base ? 1 : 0, 4, dt);
        e.action.timeScale = this.speed[name] || 1;
      }
      let sum = 0;
      for (const name in this.entries) sum += this.entries[name].once ? 0 : this.entries[name].w;
      const scale = sum > 1e-4 ? (1 - shot) / sum : 0;
      for (const name in this.entries) {
        const e = this.entries[name];
        e.action.setEffectiveWeight(e.once ? e.w : e.w * scale);
      }
      this.mixer.update(dt);
    }
  }

  C.Motion = Motion;
})(window.Atena3D);
