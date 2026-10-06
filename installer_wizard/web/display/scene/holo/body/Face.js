(function (J) {
  "use strict";
  const { THREE } = J;
  const H = (J.Holo = J.Holo || {});

  const HOLES = `
    uniform vec3 uC[3]; uniform vec2 uAx[3]; uniform vec2 uAy[3]; uniform float uOn[3];
    varying vec3 vView;
    bool inHole() {
      for (int i = 0; i < 3; i++) {
        if (uOn[i] < 0.5) continue;
        vec2 d = (vView.xy / -vView.z - uC[i].xy / -uC[i].z) * -uC[i].z;
        float u = dot(d, uAx[i]) / dot(uAx[i], uAx[i]), v = dot(d, uAy[i]) / dot(uAy[i], uAy[i]);
        if (u * u + v * v < 1.0) return true;
      }
      return false;
    }`;
  const WIRE_VERT = `
    uniform float uTime;
    varying float vFront, vY;
    varying vec3 vView;
    void main() {
      vec3 p = position + normal * sin(uTime * 2.0 + position.y * 30.0) * 0.003;
      vec4 mv = modelViewMatrix * vec4(p, 1.0);
      vView = mv.xyz;
      vec3 n = normalize(normalMatrix * normal);
      vFront = clamp(dot(n, normalize(-mv.xyz)), 0.0, 1.0);
      vY = p.y;
      gl_Position = projectionMatrix * mv;
    }`;
  const WIRE_FRAG = `
    uniform vec3 uColor; uniform float uTime, uOpacity;
    varying float vFront, vY;
    ${HOLES}
    void main() {
      if (inHole()) discard;
      float scan = smoothstep(0.04, 0.0, abs(fract(vY * 0.45 - uTime * 0.14) - 0.5) - 0.46);
      float b = 0.22 + vFront * 0.75 + scan * 0.3;
      gl_FragColor = vec4(mix(uColor, vec3(1.0), vFront * 0.25 + scan * 0.25), clamp(b, 0.0, 1.0) * uOpacity);
    }`;
  const SHELL_VERT = `
    varying float vRim;
    varying vec3 vView;
    void main() {
      vec4 mv = modelViewMatrix * vec4(position, 1.0);
      vView = mv.xyz;
      vec3 n = normalize(normalMatrix * normal);
      vRim = pow(1.0 - abs(dot(n, normalize(-mv.xyz))), 2.2);
      gl_Position = projectionMatrix * mv;
    }`;
  const SHELL_FRAG = `
    uniform vec3 uColor; uniform float uOpacity; varying float vRim;
    ${HOLES}
    void main() {
      if (inHole()) discard;
      vec3 base = vec3(0.012, 0.05, 0.09);
      gl_FragColor = vec4(mix(base, uColor, vRim * 0.6), (0.82 + vRim * 0.18) * uOpacity);
    }`;

  const holeUniforms = () => ({
    uC: { value: [new THREE.Vector3(), new THREE.Vector3(), new THREE.Vector3()] },
    uAx: { value: [new THREE.Vector2(), new THREE.Vector2(), new THREE.Vector2()] },
    uAy: { value: [new THREE.Vector2(), new THREE.Vector2(), new THREE.Vector2()] },
    uOn: { value: [1, 1, 1] },
  });

  class Face {
    constructor(avatar, geometry) {
      this.a = avatar;
      this.open = 0;
      this._mv = new THREE.Matrix4();
      this._rot = new THREE.Matrix3();
      this._v = new THREE.Vector3();
      if (geometry) {
        const shellHoles = holeUniforms(), wireHoles = holeUniforms();
        const shell = new THREE.Mesh(geometry, new THREE.ShaderMaterial({ uniforms: { ...avatar.uniforms, ...shellHoles },
          vertexShader: SHELL_VERT, fragmentShader: SHELL_FRAG, transparent: true, depthWrite: true }));
        shell.scale.setScalar(0.985);
        const wire = new THREE.Mesh(geometry, new THREE.ShaderMaterial({ uniforms: { ...avatar.uniforms, ...wireHoles },
          vertexShader: WIRE_VERT, fragmentShader: WIRE_FRAG, transparent: true, depthWrite: false, wireframe: true,
          polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1 }));
        shell.renderOrder = 0; wire.renderOrder = 1;
        shell.frustumCulled = wire.frustumCulled = false;
        this._bind(shell, shellHoles);
        this._bind(wire, wireHoles);
        avatar.body.add(shell, wire);
      }
      const L = avatar.L, floor = L.bottom - 0.12;
      const mat = new THREE.MeshBasicMaterial({ color: "#29e0ff", transparent: true, opacity: 0.25,
        blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide });
      this.rings = [0.9, 1.15, 1.4].map((r, i) => {
        const ring = new THREE.Mesh(new THREE.RingGeometry(r, r + 0.012 + i * 0.004, 128), mat.clone());
        ring.rotation.x = -Math.PI / 2;
        ring.position.y = floor;
        avatar.frame.add(ring);
        return ring;
      });
    }

    holes() {
      const L = this.a.L, F = L.F, o = this.open;
      return [
        { c: [-L.eye.x, L.eye.y - F * 0.03, L.eye.z], w: F * 0.46, h: F * 0.27 },
        { c: [L.eye.x, L.eye.y - F * 0.03, L.eye.z], w: F * 0.46, h: F * 0.27 },
        { c: [0, L.mouth.y + F * 0.06 - o * F * 0.22, L.mouth.z], w: L.mouth.w * (1.05 - o * 0.25), h: F * (0.09 + o * 0.36) },
      ];
    }

    _bind(mesh, u) {
      mesh.onBeforeRender = (renderer, scene, camera) => {
        const rig = this.a.rig;
        this._mv.multiplyMatrices(camera.matrixWorldInverse, mesh.matrixWorld);
        if (rig && rig.headMatrix) this._mv.multiply(rig.headMatrix);
        this._rot.setFromMatrix4(this._mv);
        this.holes().forEach((h, i) => {
          u.uC.value[i].set(h.c[0], h.c[1], h.c[2]).applyMatrix4(this._mv);
          this._v.set(h.w, 0, 0).applyMatrix3(this._rot);
          u.uAx.value[i].set(this._v.x, this._v.y);
          this._v.set(0, h.h, 0).applyMatrix3(this._rot);
          u.uAy.value[i].set(this._v.x, this._v.y);
        });
      };
    }

    update(t, dt, pose) {
      const a = this.a, g = a.groove, mo = 1 - a.calm * 0.6, u = a.uniforms;
      this.open = Math.max(0, Math.min(1, (pose && pose.morph && pose.morph.jawOpen) || 0));
      const fade = (1 - a.framing.closeness) * (1 - a.calm * 0.4) * u.uOpacity.value;
      this.rings.forEach((r, i) => {
        r.rotation.z = t * (0.2 + i * 0.1) * (i % 2 ? -1 : 1) * (1 + g * 2.5) * mo;
        r.material.opacity = (0.12 + 0.12 * Math.sin(t * 1.5 + i) + g * 0.2 + a.joy * 0.3) * fade;
        r.material.color.copy(u.uColor.value);
        r.visible = r.material.opacity > 0.005;
      });
    }
  }

  H.Face = Face;
})(window.Atena3D);
