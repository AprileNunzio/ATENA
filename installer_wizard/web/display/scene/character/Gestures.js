(function (J) {
  "use strict";
  const { THREE } = J;
  const C = (J.Char = J.Char || {});
  const FADE = 0.35;
  const smooth = (x) => x * x * (3 - 2 * x);

  class Gestures {
    constructor(rig) {
      this.rig = rig;
      this.list = [];
      this._v = new THREE.Vector3();
      this._w = new THREE.Vector3();
    }

    _held(side) {
      return this.list.find((g) => !g.stopping && g.pose.loop && g.sides.includes(side));
    }

    _sides(pose, wanted) {
      if (!pose.hands) return [];
      if (pose.hands === 2) return ["r", "l"];
      const first = wanted || pose.side || "r", other = first === "r" ? "l" : "r";
      if (!wanted && this._held(first) && !this._held(other)) return [other];
      return [first];
    }

    play(name, opts = {}) {
      const pose = C.Poses[name];
      if (!pose) return false;
      const sides = this._sides(pose, opts.side);
      const kept = (g) => g.persist && g.pose.loop && !pose.loop;
      const skip = sides.filter((s) => this.list.some((g) => !g.stopping && kept(g) && g.sides.includes(s)));
      for (const g of this.list) {
        if (g.name === name || (!kept(g) && g.sides.some((s) => sides.includes(s)))) g.stopping = true;
      }
      this.list.push({ name, pose, sides, skip, t: 0, w: 0, stopping: false, persist: !!opts.persist, hold: opts.hold || 0 });
      return true;
    }

    stop(name) { for (const g of this.list) if (!name || g.name === name) g.stopping = true; }
    active(name) { return this.list.some((g) => g.name === name && !g.stopping); }
    busy(side) { return this.list.some((g) => !g.stopping && g.sides.includes(side)); }
    any() { return this.list.some((g) => !g.stopping && !g.persist); }

    _vec(side, d) {
      return this._v.set(d[0] * (side === "l" ? 1 : -1), d[1], d[2]);
    }

    _arm(side, spec, w) {
      if (!spec) return;
      const p = side === "l" ? "l" : "r";
      this.rig.aim(p + "Arm", p + "Fore", this._vec(side, spec[0]), w);
      this.rig.aim(p + "Fore", p + "Hand", this._vec(side, spec[1]), w);
    }

    update(dt) {
      for (let i = this.list.length - 1; i >= 0; i--) {
        const g = this.list[i], p = g.pose;
        g.t += dt;
        if (!g.stopping && !p.loop && g.t >= p.dur - FADE) g.stopping = true;
        if (!g.stopping && g.hold && g.t >= g.hold) g.stopping = true;
        g.w = Math.max(0, Math.min(1, g.w + (g.stopping ? -dt : dt) / FADE));
        if (g.stopping && g.w <= 0) { this.list.splice(i, 1); continue; }
      }
      for (const g of this.list) {
        const out = g.pose.fn(g.t), w = smooth(g.w);
        const [main, other] = g.sides.length === 2 ? g.sides : [g.sides[0], null];
        const use = (s) => s && !g.skip.includes(s);
        if (use(main)) this._arm(main, out.main, w);
        if (use(other)) this._arm(other, out.other, w);
        for (const [k, x, y, z] of out.turns || []) this.rig.turnEuler(k, x * w, y * w, z * w);
        const curl = out.curl || {}, keep = out.keep || {};
        if (use(main) && curl.main) this.rig.curl(main, curl.main * w, keep.main);
        if (use(other) && curl.other) this.rig.curl(other, curl.other * w, keep.other);
      }
    }
  }

  C.Gestures = Gestures;
})(window.Atena3D);
