(function (J) {
  "use strict";
  const { THREE } = J;
  const H = (J.Holo = J.Holo || {});

  class Eyes {
    constructor(avatar) {
      this.a = avatar;
      const L = avatar.L, F = L.F, C = avatar.uniforms.uColor.value;
      this.mats = [];
      this.eyes = [-1, 1].map((sx) => {
        const g = new THREE.Group();
        g.position.set(sx * L.eye.x, L.eye.y, L.eye.z + F * 0.05);
        const pupil = new THREE.Mesh(new THREE.CircleGeometry(F * 0.075, 24),
          new THREE.MeshBasicMaterial({ color: C.clone(), transparent: true, opacity: 0.95, depthWrite: false }));
        pupil.renderOrder = 5;
        g.add(pupil);
        Object.assign(g, { pupil, sx });
        this.mats.push([pupil.material, 0.95]);
        avatar.headBone.add(g);
        return g;
      });
    }

    update(t, dt, pose) {
      const F = this.a.L.F, m = pose.morph, op = this.a.uniforms.uOpacity.value;
      const open = Math.max(0, Math.min(1.3, m.eyeOpen == null ? 1 : m.eyeOpen));
      this.eyes.forEach((g) => {
        g.pupil.position.set(pose.lookX * F * 0.22, pose.lookY * F * 0.12, 0);
        g.pupil.scale.set(1, Math.max(0.02, Math.min(1, open * 1.1)), 1);
        g.pupil.visible = open > 0.08;
      });
      const c = this.a.uniforms.uColor.value;
      this.mats.forEach(([mat, base]) => { mat.color.copy(c); mat.opacity = base * op; });
    }
  }

  H.Eyes = Eyes;
})(window.Atena3D);
