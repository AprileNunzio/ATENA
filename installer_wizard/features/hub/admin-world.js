(() => {
  const A = window.AtenaAdmin;
  const CYAN = 0x29e0ff, VIOLET = 0xa08cff, GREEN = 0x3dffa8, AMBER = 0xffc43d;

  function load(src) {
    return new Promise((ok, fail) => {
      if (document.querySelector(`script[data-src="${src}"]`)) { ok(); return; }
      const s = document.createElement("script");
      s.src = src; s.dataset.src = src; s.onload = ok; s.onerror = () => fail(new Error(`${src} non disponibile`));
      document.head.appendChild(s);
    });
  }

  async function libraries() {
    if (!window.THREE) await load("/vendor/three.min.js");
    if (!window.THREE.OrbitControls) await load("/vendor/OrbitControls.js");
  }

  function supported() {
    try { const c = document.createElement("canvas"); return !!(c.getContext("webgl2") || c.getContext("webgl")); } catch { return false; }
  }

  function label(raw, opts = {}) {
    const text = (window.AtenaI18n && window.AtenaI18n.translate(raw)) || raw;
    const T = window.THREE, size = opts.size || 30, pad = 14;
    const canvas = document.createElement("canvas"), ctx = canvas.getContext("2d");
    ctx.font = `600 ${size}px system-ui, sans-serif`;
    const width = Math.min(900, Math.ceil(ctx.measureText(text).width) + pad * 2);
    canvas.width = width; canvas.height = size + pad * 2;
    ctx.font = `600 ${size}px system-ui, sans-serif`;
    ctx.fillStyle = opts.bg || "rgba(4,14,26,0.82)";
    ctx.strokeStyle = opts.border || "rgba(41,224,255,0.65)"; ctx.lineWidth = 3;
    const r = 14;
    ctx.beginPath(); ctx.roundRect ? ctx.roundRect(2, 2, width - 4, canvas.height - 4, r) : ctx.rect(2, 2, width - 4, canvas.height - 4);
    ctx.fill(); ctx.stroke();
    ctx.fillStyle = opts.color || "#dff6ff"; ctx.textBaseline = "middle";
    ctx.fillText(text, pad, canvas.height / 2 + 1, width - pad * 2);
    const tex = new T.CanvasTexture(canvas); tex.minFilter = T.LinearFilter;
    const sprite = new T.Sprite(new T.SpriteMaterial({ map: tex, transparent: true, depthWrite: false }));
    const scale = (opts.scale || 0.02);
    sprite.scale.set(width * scale, canvas.height * scale, 1);
    sprite.renderOrder = 10;
    return sprite;
  }

  function glowMat(color, intensity = 0.6) {
    const T = window.THREE;
    return new T.MeshStandardMaterial({ color, emissive: color, emissiveIntensity: intensity, roughness: 0.4, metalness: 0.2 });
  }

  function road(scene, count) {
    const T = window.THREE;
    const pts = [];
    for (let i = 0; i < count; i++) {
      const x = -22 + (44 * i) / (count - 1);
      pts.push(new T.Vector3(x, 0.05, Math.sin(i * 0.9) * 3.2 + 6));
    }
    const curve = new T.CatmullRomCurve3(pts);
    const tube = new T.Mesh(new T.TubeGeometry(curve, 200, 1.1, 8, false), new T.MeshStandardMaterial({ color: 0x0b1d2c, roughness: 0.9 }));
    tube.scale.y = 0.08; scene.add(tube);
    const line = new T.Line(new T.BufferGeometry().setFromPoints(curve.getPoints(300)), new T.LineDashedMaterial({ color: CYAN, dashSize: 0.6, gapSize: 0.5 }));
    line.computeLineDistances(); line.position.y = 0.16; scene.add(line);
    return curve;
  }

  function gate(scene, pos, text, index, total) {
    const T = window.THREE, group = new T.Group();
    const color = index === total - 1 ? GREEN : index === 0 ? CYAN : VIOLET;
    const pillar = new T.BoxGeometry(0.25, 2.4, 0.25);
    [-1.5, 1.5].forEach((dz) => { const m = new T.Mesh(pillar, glowMat(color, 0.35)); m.position.set(0, 1.2, dz); group.add(m); });
    const beam = new T.Mesh(new T.BoxGeometry(0.3, 0.22, 3.3), glowMat(color, 0.9)); beam.position.y = 2.45; group.add(beam);
    const tag = label(text, { size: 28 }); tag.position.set(0, 3.4, 0); group.add(tag);
    group.position.copy(pos); scene.add(group);
    return { group, beam, color };
  }

  function building(scene, spec) {
    const T = window.THREE, group = new T.Group();
    const h = spec.h || 3;
    const body = new T.Mesh(new T.BoxGeometry(spec.w || 3, h, spec.d || 3),
      new T.MeshStandardMaterial({ color: 0x0d2233, emissive: spec.color, emissiveIntensity: 0.08, roughness: 0.5, metalness: 0.4, transparent: true, opacity: 0.92 }));
    body.position.y = h / 2; group.add(body);
    const edges = new T.LineSegments(new T.EdgesGeometry(body.geometry), new T.LineBasicMaterial({ color: spec.color }));
    edges.position.copy(body.position); group.add(edges);
    const roof = new T.Mesh(new T.CylinderGeometry(0.35, 0.35, 0.12, 24), glowMat(spec.color, 1)); roof.position.y = h + 0.1; group.add(roof);
    const tag = label(`${spec.icon} ${spec.title}`, { size: 30, border: "rgba(160,140,255,0.6)" }); tag.position.y = h + 1.1; group.add(tag);
    group.position.set(spec.x, 0, spec.z);
    group.userData = { tab: spec.tab, feature: spec.feature, body, roof, base: h };
    scene.add(group);
    return group;
  }

  function create(host, opts) {
    const T = window.THREE;
    const renderer = new T.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    host.appendChild(renderer.domElement);
    const scene = new T.Scene();
    scene.fog = new T.Fog(0x02070d, 40, 90);
    const camera = new T.PerspectiveCamera(42, 1, 0.1, 200);
    camera.position.set(0, 21, 27);
    const controls = new T.OrbitControls(camera, renderer.domElement);
    controls.target.set(0, 0, 0); controls.enableDamping = true; controls.maxPolarAngle = Math.PI * 0.46;
    controls.minDistance = 14; controls.maxDistance = 70; controls.autoRotate = !opts.still; controls.autoRotateSpeed = 0.25;
    scene.add(new T.HemisphereLight(0x6fd8ff, 0x050a12, 0.55));
    const sun = new T.DirectionalLight(0xffffff, 0.7); sun.position.set(10, 30, 15); scene.add(sun);
    const ground = new T.Mesh(new T.CircleGeometry(48, 64), new T.MeshStandardMaterial({ color: 0x03101b, roughness: 1 }));
    ground.rotation.x = -Math.PI / 2; scene.add(ground);
    const grid = new T.GridHelper(96, 48, 0x0f3a52, 0x0a2436); grid.position.y = 0.01; scene.add(grid);

    const curve = road(scene, opts.stations.length);
    const gates = opts.stations.map((s, i) => gate(scene, curve.getPoint(i / (opts.stations.length - 1)), s.label, i, opts.stations.length));
    const districts = (opts.districts || []).map((d) => building(scene, d));

    const ray = new T.Raycaster(), mouse = new T.Vector2();
    let hovered = null;
    function pick(ev) {
      const r = renderer.domElement.getBoundingClientRect();
      mouse.set(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
      ray.setFromCamera(mouse, camera);
      const hit = ray.intersectObjects(districts.map((d) => d.userData.body), false)[0];
      return hit ? districts.find((d) => d.userData.body === hit.object) : null;
    }
    renderer.domElement.addEventListener("pointermove", (ev) => {
      const d = pick(ev);
      if (hovered && hovered !== d) hovered.userData.body.material.emissiveIntensity = 0.08;
      hovered = d; renderer.domElement.style.cursor = d ? "pointer" : "grab";
      if (d) d.userData.body.material.emissiveIntensity = 0.35;
    });
    renderer.domElement.addEventListener("click", (ev) => { const d = pick(ev); if (d && opts.onPick) opts.onPick(d.userData); });
    renderer.domElement.addEventListener("pointerdown", () => { controls.autoRotate = false; });

    function resize() {
      const w = host.clientWidth || 600, h = host.clientHeight || 400;
      renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix();
    }
    const observer = new ResizeObserver(resize); observer.observe(host); resize();

    const tickers = [];
    let raf = 0, last = performance.now(), running = false;
    function frame(now) {
      const dt = Math.min(0.1, (now - last) / 1000); last = now;
      tickers.forEach((fn) => fn(dt, now / 1000));
      districts.forEach((d, i) => { d.userData.roof.position.y = d.userData.base + 0.1 + Math.sin(now / 600 + i) * 0.08; });
      controls.update(); renderer.render(scene, camera);
      if (running) raf = requestAnimationFrame(frame);
    }
    return {
      scene, curve, gates, label, glowMat, colors: { CYAN, VIOLET, GREEN, AMBER },
      tick(fn) { tickers.push(fn); },
      start() { if (!running) { running = true; last = performance.now(); raf = requestAnimationFrame(frame); } },
      stop() { running = false; cancelAnimationFrame(raf); },
      dispose() { this.stop(); observer.disconnect(); controls.dispose(); renderer.dispose(); renderer.domElement.remove(); },
    };
  }

  A.hubWorld = { libraries, supported, create, label };
})();
