(function (J) {
  "use strict";
  const { THREE, damp } = J;
  const H = J.Holo, C = J.Char;
  const MODEL = "/vendor/Michelle.glb", MOTIONS = "/vendor/Xbot.glb";

  function load(url) {
    return new Promise((ok, ko) => new THREE.GLTFLoader().load(url, ok, undefined, () => ko(new Error(`${url} non caricato`))));
  }

  function shadowTexture() {
    const c = document.createElement("canvas");
    c.width = c.height = 128;
    const g = c.getContext("2d"), r = g.createRadialGradient(64, 64, 0, 64, 64, 64);
    r.addColorStop(0, "rgba(0,0,0,0.55)"); r.addColorStop(0.6, "rgba(0,0,0,0.18)"); r.addColorStop(1, "rgba(0,0,0,0)");
    g.fillStyle = r; g.fillRect(0, 0, 128, 128);
    return new THREE.CanvasTexture(c);
  }

  class CharacterAvatar {
    constructor(parent, onReady, options = {}) {
      this.parent = parent;
      this.options = options;
      this.group = new THREE.Group();
      this.frame = new THREE.Group();
      this.body = new THREE.Group();
      this.facing = new THREE.Group();
      this.headBone = new THREE.Group();
      this.headBone.matrixAutoUpdate = false;
      this.facing.add(this.headBone);
      this.body.add(this.facing);
      this.frame.add(this.body);
      this.group.add(this.frame);
      parent.add(this.group);
      this.uniforms = { uTime: { value: 0 }, uOpacity: { value: 0 }, uColor: { value: new THREE.Color(options.color || "#29e0ff") } };
      this.opacity = 1; this.jawTarget = 0; this.ready = false;
      this.realAudio = false; this.listening = false; this.thinking = false;
      this.groove = 0; this.grooveTarget = 0; this.joy = 0; this.calm = 0; this.calmTarget = 0;
      this.pose = H.blankPose();
      this.gaze = new H.Gaze();
      this.visemes = new H.Visemes();
      this.animator = new H.Animator((name, arg) => this.toggleAccessory(name, arg));
      this.director = new H.Director(this);
      this.parts = []; this.accessories = {}; this.materials = []; this.morphs = [];
      this.umbrella = new C.Umbrella(this.facing);
      this.rain = new C.Rain(this.facing);
      this.life = new C.Life(this);
      this._lights();
      if (options.renderer) this.attachRenderer(options.renderer);
      this._load(options).then(() => onReady && onReady()).catch((err) => {
        console.warn("Personaggio 3D non disponibile", err);
        parent.remove(this.group);
        if (options.onFail) options.onFail(err);
      });
    }

    attachRenderer(renderer) {
      renderer.outputEncoding = THREE.sRGBEncoding;
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
      renderer.toneMappingExposure = 1.05;
      if (THREE.RoomEnvironment && this.parent.isScene && !this.parent.environment) {
        const pm = new THREE.PMREMGenerator(renderer);
        this.parent.environment = pm.fromScene(new THREE.RoomEnvironment(), 0.04).texture;
        pm.dispose();
      }
    }

    _lights() {
      const hemi = new THREE.HemisphereLight("#dceeff", "#1b2633", 0.65);
      const key = new THREE.DirectionalLight("#fff3e6", 1.25);
      key.position.set(2.2, 3.5, 4);
      const fill = new THREE.DirectionalLight("#bcd8ff", 0.35);
      fill.position.set(-3, 1.5, 2);
      this.rim = new THREE.DirectionalLight(this.uniforms.uColor.value.clone(), 1.1);
      this.rim.position.set(-1.5, 2.5, -3.5);
      this.lights = [hemi, key, fill, this.rim];
      this.group.add(...this.lights);
      const shadow = new THREE.Mesh(new THREE.PlaneGeometry(1.5, 1.5),
        new THREE.MeshBasicMaterial({ map: shadowTexture(), transparent: true, depthWrite: false, toneMapped: false }));
      shadow.rotation.x = -Math.PI / 2;
      shadow.position.y = -0.995;
      this.shadow = shadow;
      this.facing.add(shadow);
    }

    async _load(options) {
      const gltf = await load(options.character || MODEL);
      const root = gltf.scene;
      root.updateMatrixWorld(true);
      const box = new THREE.Box3(), v = new THREE.Vector3();
      root.traverse((o) => { if (o.isBone) box.expandByPoint(o.getWorldPosition(v)); });
      if (box.isEmpty()) throw new Error("il modello non ha uno scheletro");
      const s = 2 / Math.max(1e-6, box.max.y - box.min.y), hips = new THREE.Vector3();
      root.scale.multiplyScalar(s);
      this.facing.add(root);
      this.root = root;
      this.rig = new C.Rig(root, this.facing);
      if (!this.rig.ok) throw new Error("scheletro umanoide non riconosciuto");
      this.rig.bones.hips.getWorldPosition(hips);
      root.position.set(-hips.x * s, -1 - box.min.y * s, -hips.z * s);
      this._materials(root);
      this.motion = new C.Motion(root).add(gltf.animations.map((c) => C.nativeClip(c, root)));
      try {
        const lib = await load(options.motions || MOTIONS);
        const clips = lib.animations.map((c) => C.retarget(c, lib.scene, root)).filter(Boolean);
        this.motion.add(clips);
      } catch (err) {
        console.warn("Animazioni del personaggio non disponibili: uso le pose procedurali", err);
      }
      this.gestures = new C.Gestures(this.rig);
      if (!this.motion.ready()) this.gestures.play("riposo", { persist: true });
      this.rig.sync();
      this.restHead = this.rig.matrix("head", new THREE.Matrix4()).invert();
      this.headMatrix = new THREE.Matrix4();
      this._hm = new THREE.Matrix4();
      const headPos = this.rig.pos("head", new THREE.Vector3());
      this.L = H.Landmarks.fromHead(new THREE.Box3(new THREE.Vector3(-0.5, -1, -0.3), new THREE.Vector3(0.5, 1, 0.3)), headPos);
      this.framing = new H.Framing(this.frame, this.L);
      this.parts.push(new H.Face(this, null));
      for (const name in H.Accessories) this.accessories[name] = H.Accessories[name](this);
      this.parts.push(...Object.values(this.accessories));
      this.ready = true;
      if (this.pendingWeather !== undefined) this.setWeather(this.pendingWeather);
    }

    _materials(root) {
      const map = H.MORPHS || {};
      root.traverse((o) => {
        if (!o.isMesh) return;
        o.frustumCulled = false;
        for (const m of [].concat(o.material)) { m.envMapIntensity = 0.85; this.materials.push(m); }
        if (o.morphTargetDictionary) {
          const idx = {};
          for (const k in map) idx[k] = map[k].map((n) => o.morphTargetDictionary[n]).filter((i) => i !== undefined);
          this.morphs.push({ m: o, idx });
        }
      });
    }

    play(name) {
      const k = C.Actions.key(name), act = C.Actions.ACTIONS[k];
      if (act && this.ready) { act(this); return true; }
      return this.animator.play(name);
    }

    stop(name) {
      if (!name) { this.gestures && this.gestures.stop(); this.life.dance(false); this.animator.stop(); return; }
      const k = C.Actions.key(name);
      if (C.Actions.STOPS[k]) C.Actions.STOPS[k](this);
      if (this.gestures) this.gestures.stop(k);
      this.animator.stop(name);
    }

    express(name, seconds = 2.5) {
      const ok = this.animator.express(name, seconds);
      const e = C.Actions.EXPRESS[String(name || "").toLowerCase()];
      if (e && this.ready) e(this, seconds);
      return ok || this.play(name);
    }

    shot(name, seconds) { return !!this.framing && this.framing.set(name, seconds); }
    setContext(mode) { if (this.framing) this.framing.setContext(mode); }
    direct(text) { this.director.react(text); }
    setVoice(bands) { this.visemes.setBands(bands); }
    setGaze(x, y) { this.gaze.set(x, y); }
    setGroove(v) { this.grooveTarget = Math.max(this.grooveTarget, Math.min(1, v || 0)); }
    setCalm(on) { this.calmTarget = on ? 1 : 0; }
    burst() { this.joy = 1; }
    sing(on) { if (on) this.play("canta"); else this.stop("canta"); }
    dance(on) { this.life.dance(on); }
    setColor(hex) { this.targetColor = new THREE.Color(hex); }
    toggleAccessory(name, state) { const a = this.accessories[name]; if (a) a.toggle(state); }
    setWeather(icon) { if (this.ready) this.life.setWeather(icon); else this.pendingWeather = icon; }

    catalog() {
      return { ...H.Library.catalog(), corpo: C.Actions.names(), accessori: Object.keys(this.accessories),
               inquadrature: ["intera", "mezzo", "primo_piano"] };
    }

    _head(p) {
      const r = this.rig;
      r.turnEuler("neck", p.rx * 0.4, p.ry * 0.4, p.rz * 0.4);
      r.turnEuler("head", p.rx * 0.6, p.ry * 0.6, p.rz * 0.6);
    }

    _morph(morph) {
      for (const { m, idx } of this.morphs) {
        const inf = m.morphTargetInfluences;
        for (const k in idx) for (const i of idx[k]) inf[i] = 0;
        for (const k in idx) {
          const w = Math.max(0, Math.min(1, morph[k] || 0));
          for (const i of idx[k]) inf[i] = Math.max(inf[i], w);
        }
      }
    }

    _fade(o) {
      const see = o < 0.999;
      for (const m of this.materials) {
        if (m.transparent !== see) { m.transparent = see; m.needsUpdate = true; }
        m.opacity = o;
      }
      this.shadow.material.opacity = o;
    }

    update(t, dt, speaking) {
      const u = this.uniforms;
      u.uTime.value = t;
      u.uOpacity.value = damp(u.uOpacity.value, this.ready ? this.opacity : 0, 3, dt);
      if (this.targetColor) { u.uColor.value.lerp(this.targetColor, 1 - Math.exp(-3 * dt)); this.rim.color.copy(u.uColor.value); }
      this.grooveTarget = damp(this.grooveTarget, 0, 2.5, dt);
      this.groove = damp(this.groove, this.grooveTarget, 12, dt);
      this.joy = damp(this.joy, 0, 1.6, dt);
      this.calm = damp(this.calm, this.calmTarget, 0.8, dt);
      this.group.visible = this.ready && u.uOpacity.value > 0.01;
      if (!this.group.visible) return;
      const st = { speaking, listening: this.listening, thinking: this.thinking, groove: this.groove,
                   joy: this.joy, calm: this.calm, jaw: this.visemes.open };
      this.gaze.update(t, dt, this.thinking);
      this.animator.update(t, dt, st, this.pose, this.gaze);
      this.visemes.update(t, dt, speaking, this, this.pose.morph);
      this.animator.finish(this.pose, this.calm);
      this.life.update(t, dt, st);
      if (!this.motion.ready()) this.rig.restPose();
      this.motion.update(dt);
      this.rig.sync();
      this.gestures.update(dt);
      this._head(this.pose);
      this._morph(this.pose.morph);
      this.headMatrix.multiplyMatrices(this.rig.matrix("head", this._hm), this.restHead);
      this.headBone.matrix.copy(this.headMatrix);
      this.headBone.matrixWorldNeedsUpdate = true;
      this.umbrella.update(dt, this.rig);
      this.rain.update(dt, this.umbrella.shelter());
      this.framing.update(dt, speaking);
      for (const p of this.parts) p.update(t, dt, this.pose);
      this._fade(u.uOpacity.value);
    }
  }

  J.CharacterAvatar = CharacterAvatar;
  C.CharacterAvatar = CharacterAvatar;
})(window.Atena3D);
