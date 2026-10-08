(function (J) {
  "use strict";
  const { THREE, damp } = J;
  const C = (J.Char = J.Char || {});
  const COUNT = 700, BOX = { x: 1.9, z: 1.2, top: 1.6, floor: -1.02 };

  class Rain {
    constructor(parent) {
      this.level = 0; this.target = 0; this.wind = 0.12;
      this.drops = new Float32Array(COUNT * 4);
      for (let i = 0; i < COUNT; i++) this._spawn(i, true);
      this.pos = new Float32Array(COUNT * 6);
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.BufferAttribute(this.pos, 3).setUsage(THREE.DynamicDrawUsage));
      this.mat = new THREE.LineBasicMaterial({ color: "#a9dcff", transparent: true, opacity: 0, depthWrite: false });
      this.lines = new THREE.LineSegments(g, this.mat);
      this.lines.frustumCulled = false;
      this.lines.visible = false;
      parent.add(this.lines);
      this.splash = this._splashes(parent);
    }

    _splashes(parent) {
      const g = new THREE.BufferGeometry(), n = 60;
      this.splashData = new Float32Array(n * 4);
      this.splashPos = new Float32Array(n * 3);
      g.setAttribute("position", new THREE.BufferAttribute(this.splashPos, 3).setUsage(THREE.DynamicDrawUsage));
      const m = new THREE.PointsMaterial({ color: "#d6f0ff", size: 0.025, transparent: true, opacity: 0, depthWrite: false });
      const p = new THREE.Points(g, m);
      p.frustumCulled = false;
      parent.add(p);
      this.splashNext = 0;
      return p;
    }

    _spawn(i, scatter) {
      const d = this.drops, o = i * 4;
      d[o] = (Math.random() * 2 - 1) * BOX.x;
      d[o + 1] = scatter ? BOX.floor + Math.random() * (BOX.top - BOX.floor) : BOX.top + Math.random() * 0.4;
      d[o + 2] = (Math.random() * 2 - 1) * BOX.z;
      d[o + 3] = 5.5 + Math.random() * 2.5;
    }

    _splashAt(x, y, z) {
      const n = this.splashData.length / 4, o = (this.splashNext++ % n) * 4;
      this.splashData[o] = x; this.splashData[o + 1] = y; this.splashData[o + 2] = z; this.splashData[o + 3] = 0.25;
    }

    set(level) { this.target = Math.max(0, Math.min(1, level || 0)); }

    update(dt, shelter) {
      this.level = damp(this.level, this.target, 1.5, dt);
      const on = this.level > 0.01;
      this.lines.visible = this.splash.visible = on;
      if (!on) return;
      const active = Math.floor(COUNT * this.level), d = this.drops, P = this.pos, len = 0.09;
      for (let i = 0; i < COUNT; i++) {
        const o = i * 4, q = i * 6;
        if (i >= active) { P[q + 1] = P[q + 4] = -50; continue; }
        d[o + 1] -= d[o + 3] * dt;
        d[o] += this.wind * dt;
        let hit = d[o + 1] < BOX.floor;
        if (!hit && shelter) {
          const dx = d[o] - shelter.x, dz = d[o + 2] - shelter.z;
          if (dx * dx + dz * dz < shelter.r * shelter.r && d[o + 1] < shelter.y - 0.04 && d[o + 1] > shelter.y - 0.3) hit = true;
        }
        if (hit) {
          if (Math.random() < 0.25) this._splashAt(d[o], d[o + 1], d[o + 2]);
          this._spawn(i, false);
        }
        if (d[o] > BOX.x) d[o] -= BOX.x * 2;
        P[q] = d[o]; P[q + 1] = d[o + 1]; P[q + 2] = d[o + 2];
        P[q + 3] = d[o] - this.wind * 0.02; P[q + 4] = d[o + 1] + len; P[q + 5] = d[o + 2];
      }
      this.lines.geometry.attributes.position.needsUpdate = true;
      const S = this.splashData, SP = this.splashPos;
      for (let i = 0; i < S.length / 4; i++) {
        const o = i * 4, q = i * 3;
        S[o + 3] = Math.max(0, S[o + 3] - dt);
        const life = S[o + 3];
        SP[q] = S[o]; SP[q + 1] = life > 0 ? S[o + 1] + (0.25 - life) * 0.25 : -50; SP[q + 2] = S[o + 2];
      }
      this.splash.geometry.attributes.position.needsUpdate = true;
      this.mat.opacity = 0.55 * this.level;
      this.splash.material.opacity = 0.7 * this.level;
    }
  }

  C.Rain = Rain;
})(window.Atena3D);
