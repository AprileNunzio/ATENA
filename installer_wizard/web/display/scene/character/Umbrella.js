(function (J) {
  "use strict";
  const { THREE, damp } = J;
  const C = (J.Char = J.Char || {});
  const RIBS = 8, RADIUS = 0.66, DEPTH = 0.27, CLOSED = [0.05, 0.62];
  const UP = new THREE.Vector3(0, 1, 0);

  function canopyGeometry() {
    const g = new THREE.ConeGeometry(1, 1, RIBS * 2, 3, true);
    const p = g.attributes.position;
    for (let i = 0; i < p.count; i++) {
      const x = p.getX(i), z = p.getZ(i), y = p.getY(i);
      const a = Math.atan2(z, x), r = Math.hypot(x, z), sag = r * 0.12 * (1 - Math.cos(a * RIBS)) * 0.5;
      p.setY(i, y - 0.5 - sag);
    }
    g.computeVertexNormals();
    return g;
  }

  function ribsGeometry() {
    const v = [];
    for (let i = 0; i < RIBS; i++) {
      const a = (i / RIBS) * Math.PI * 2;
      v.push(0, 0, 0, Math.cos(a), -1, Math.sin(a));
    }
    return new THREE.BufferGeometry().setAttribute("position", new THREE.Float32BufferAttribute(v, 3));
  }

  class Umbrella {
    constructor(parent, color = "#e8423f") {
      this.on = false; this.appear = 0; this.open = 0;
      this.group = new THREE.Group();
      this.group.visible = false;
      const fabric = new THREE.MeshStandardMaterial({ color, roughness: 0.55, metalness: 0.05, side: THREE.DoubleSide });
      const metal = new THREE.MeshStandardMaterial({ color: "#c9ced6", roughness: 0.3, metalness: 0.85 });
      const grip = new THREE.MeshStandardMaterial({ color: "#2a1d17", roughness: 0.45 });
      const shaftGeo = new THREE.CylinderGeometry(0.009, 0.009, 1, 10);
      shaftGeo.translate(0, 0.5, 0);
      this.shaft = new THREE.Mesh(shaftGeo, metal);
      this.handle = new THREE.Mesh(new THREE.TorusGeometry(0.055, 0.016, 10, 20, Math.PI), grip);
      this.handle.rotation.z = Math.PI;
      this.handle.position.set(0.055, -0.11, 0);
      const stem = new THREE.Mesh(new THREE.CylinderGeometry(0.017, 0.017, 0.16, 10), grip);
      stem.position.y = -0.04;
      this.top = new THREE.Group();
      this.canopy = new THREE.Mesh(canopyGeometry(), fabric);
      this.ribs = new THREE.LineSegments(ribsGeometry(), new THREE.LineBasicMaterial({ color: "#7d1d1b" }));
      const tip = new THREE.Mesh(new THREE.CylinderGeometry(0.004, 0.01, 0.06, 8), metal);
      tip.position.y = 0.03;
      this.cloth = new THREE.Group();
      this.cloth.add(this.canopy, this.ribs);
      this.top.add(this.cloth, tip);
      this.group.add(this.shaft, this.handle, stem, this.top);
      this.group.traverse((o) => { if (o.isMesh) o.castShadow = false; });
      parent.add(this.group);
      this._g = new THREE.Vector3(); this._m = new THREE.Vector3(); this._top = new THREE.Vector3(); this._d = new THREE.Vector3();
    }

    set(on) { this.on = !!on; }
    get active() { return this.on || this.appear > 0.02; }

    shelter() {
      if (this.open < 0.5 || !this.group.visible) return null;
      return { x: this._top.x, z: this._top.z, y: this._top.y, r: RADIUS * this.open * this.appear };
    }

    update(dt, rig) {
      this.appear = damp(this.appear, this.on || this.open > 0.08 ? 1 : 0, 5, dt);
      this.open = damp(this.open, this.on && this.appear > 0.85 ? 1 : 0, 3.4, dt);
      this.group.visible = this.appear > 0.02;
      if (!this.group.visible || !rig.has("rHand")) return;
      rig.pos("rHand", this._g);
      if (rig.has("rMiddle1")) this._g.lerp(rig.pos("rMiddle1", this._m), 0.55);
      if (rig.has("headTop")) rig.pos("headTop", this._top); else rig.pos("head", this._top).y += 0.25;
      this._top.y += 0.36; this._top.z += 0.03;
      this._d.subVectors(this._top, this._g);
      const len = Math.max(0.3, this._d.length());
      this.group.position.copy(this._g);
      this.group.quaternion.setFromUnitVectors(UP, this._d.normalize());
      const pop = this.appear < 1 ? 1 + Math.sin(this.appear * Math.PI) * 0.12 : 1;
      this.group.scale.setScalar(this.appear * pop);
      this.shaft.scale.y = len;
      this.top.position.y = len;
      const o = this.open, r = CLOSED[0] + (RADIUS - CLOSED[0]) * o, h = CLOSED[1] + (DEPTH - CLOSED[1]) * o;
      this.cloth.scale.set(r, h, r);
      this.cloth.rotation.y += dt * (1 - o) * 0.6;
    }
  }

  C.Umbrella = Umbrella;
})(window.Atena3D);
