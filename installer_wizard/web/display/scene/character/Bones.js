(function (J) {
  "use strict";
  const { THREE } = J;
  const C = (J.Char = J.Char || {});
  const BASE = { hips: "hips", spine: "spine", chest: "spine1", upper: "spine2", neck: "neck", head: "head", headTop: "headtopend" };
  const SIDE = { Shoulder: "shoulder", Arm: "arm", Fore: "forearm", Hand: "hand", UpLeg: "upleg", Leg: "leg", Foot: "foot" };
  const FINGERS = ["Thumb", "Index", "Middle", "Ring", "Pinky"];
  const BEND = [0.9, 1.25, 0.85];
  const REQUIRED = ["hips", "spine", "neck", "head", "lArm", "lFore", "lHand", "rArm", "rFore", "rHand"];

  const canon = (name) => String(name || "").toLowerCase().replace(/^mixamorig\d*/, "").replace(/[^a-z0-9]/g, "");

  function table() {
    const t = { ...BASE };
    for (const [s, w] of [["l", "left"], ["r", "right"]]) {
      for (const k in SIDE) t[s + k] = w + SIDE[k];
      for (const f of FINGERS) for (let i = 1; i <= 3; i++) t[`${s}${f}${i}`] = `${w}hand${f.toLowerCase()}${i}`;
    }
    return t;
  }
  const TABLE = table();

  function byCanon(root) {
    const map = {};
    root.traverse((o) => { if (o.isBone) { const c = canon(o.name); if (!map[c]) map[c] = o; } });
    return map;
  }

  class Rig {
    constructor(root, space) {
      this.root = root;
      this.space = space;
      this.all = byCanon(root);
      this.bones = {};
      for (const k in TABLE) if (this.all[TABLE[k]]) this.bones[k] = this.all[TABLE[k]];
      this.ok = REQUIRED.every((k) => this.bones[k]);
      this.rest = {};
      for (const k in this.bones) this.rest[k] = this.bones[k].quaternion.clone();
      this._inv = new THREE.Matrix4();
      this._spaceQ = new THREE.Quaternion();
      this._m = new THREE.Matrix4();
      this._p = new THREE.Vector3(); this._s = new THREE.Vector3();
      this._qa = new THREE.Quaternion(); this._qb = new THREE.Quaternion(); this._qc = new THREE.Quaternion();
      this._id = new THREE.Quaternion();
      this._a = new THREE.Vector3(); this._b = new THREE.Vector3(); this._c = new THREE.Vector3();
      this._d = new THREE.Vector3(); this._t = new THREE.Vector3(); this._e = new THREE.Euler();
    }

    has(k) { return !!this.bones[k]; }

    sync() {
      this.space.updateWorldMatrix(true, false);
      this._inv.copy(this.space.matrixWorld).invert();
      this.space.matrixWorld.decompose(this._p, this._spaceQ, this._s);
      this._spaceQ.invert();
      this.root.updateMatrixWorld(true);
    }

    pos(k, out) {
      const b = this.bones[k];
      return b ? out.setFromMatrixPosition(b.matrixWorld).applyMatrix4(this._inv) : null;
    }

    quat(obj, out) {
      obj.matrixWorld.decompose(this._p, out, this._s);
      return out.premultiply(this._spaceQ);
    }

    matrix(k, out) {
      return out.multiplyMatrices(this._inv, this.bones[k].matrixWorld);
    }

    _set(bone, q) {
      this.quat(bone.parent, this._qc);
      bone.quaternion.copy(this._qc.invert().multiply(q));
      bone.updateMatrixWorld(true);
    }

    turn(k, delta, w = 1) {
      const b = this.bones[k];
      if (!b || w <= 0.001) return;
      this._qb.copy(this._id).slerp(delta, Math.min(1, w));
      this.quat(b, this._qa);
      this._set(b, this._qa.premultiply(this._qb));
    }

    turnEuler(k, x, y, z, w = 1) {
      this._e.set(x, y, z);
      this.turn(k, this._qa.setFromEuler(this._e), w);
    }

    aim(k, childK, dir, w = 1) {
      if (!this.bones[k] || !this.bones[childK] || w <= 0.001) return;
      this.pos(k, this._a); this.pos(childK, this._b);
      this._d.subVectors(this._b, this._a).normalize();
      this._t.copy(dir).normalize();
      const q = new THREE.Quaternion().setFromUnitVectors(this._d, this._t);
      this.turn(k, q, w);
    }

    curl(side, amount, keep) {
      if (amount <= 0.01 || !this.bones[side + "Middle1"] || !this.bones[side + "Index1"] || !this.bones[side + "Pinky1"]) return;
      const hand = this.pos(side + "Hand", new THREE.Vector3());
      const along = this.pos(side + "Middle1", new THREE.Vector3()).sub(hand).normalize();
      const across = this.pos(side + "Index1", new THREE.Vector3()).sub(this.pos(side + "Pinky1", new THREE.Vector3())).normalize();
      const palm = new THREE.Vector3().crossVectors(along, across).multiplyScalar(side === "l" ? -1 : 1);
      const q = new THREE.Quaternion(), axis = new THREE.Vector3();
      for (const f of FINGERS) {
        if (keep && keep.includes(f)) continue;
        const amt = f === "Thumb" ? amount * 0.55 : amount;
        for (let i = 1; i <= 3; i++) {
          const k = side + f + i, b = this.bones[k];
          if (!b || !b.children[0]) continue;
          this.pos(k, this._a);
          this._b.setFromMatrixPosition(b.children[0].matrixWorld).applyMatrix4(this._inv);
          this._d.subVectors(this._b, this._a).normalize();
          axis.crossVectors(this._d, palm);
          if (axis.lengthSq() < 1e-6) continue;
          this.turn(k, q.setFromAxisAngle(axis.normalize(), amt * BEND[i - 1]));
        }
      }
    }

    restPose() { for (const k in this.bones) this.bones[k].quaternion.copy(this.rest[k]); }
  }

  C.Rig = Rig;
  C.canon = canon;
  C.byCanon = byCanon;
})(window.Atena3D);
