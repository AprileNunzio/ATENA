(() => {
  const D = window.AtenaDisplay, { $ } = D;
  const V = window.ATENA_ASSET_V ? `?v=${window.ATENA_ASSET_V}` : "";
  const loadScript = (src) => new Promise((ok, ko) => {
    const el = document.createElement("script");
    el.src = src + V; el.onload = ok; el.onerror = () => ko(new Error(`${src} non caricato`));
    document.head.appendChild(el);
  });
  let lib3d = null;
  const LIB_3D = [
    "/vendor/three.min.js", "/vendor/OrbitControls.js", "/vendor/GLTFLoader.js", "/vendor/RoomEnvironment.js",
    ...["common", "brain"].map((m) => `/static/display/scene/${m}.js`),
    ...[
      "rig/Landmarks", "rig/Shapes", "rig/MeshRig", "rig/NativeRig", "rig/Visemes",
      "anim/Library", "anim/Animator", "anim/Gaze", "camera/Framing",
      "body/Face", "body/Eyes",
      "accessories/Accessory", "accessories/Hat", "accessories/Glasses", "accessories/Headphones",
      "Director", "HoloAvatar",
    ].map((m) => `/static/display/scene/holo/${m}.js`),
    ...["Bones", "Retarget", "Motion", "Poses", "Gestures", "Umbrella", "Rain", "Life", "Actions", "CharacterAvatar"]
      .map((m) => `/static/display/scene/character/` + m + ".js"),
    "/static/display/scene/scene.js"
  ];
  const load3D = () => lib3d || (lib3d = LIB_3D.reduce((p, src) => p.then(() => loadScript(src)), Promise.resolve()));

  function startLight() {
    $("scene").style.display = "none"; $("core").style.display = "block";
    if (window.atenaPerf) window.atenaPerf.lite(D.look.reason || "modalità leggera");
    D.avatar = window.atenaAvatar = new AtenaAvatar.ThoughtCore($("core"));
    D.avatar.setMode(D.mode);
  }

  async function startFull() {
    const { FACE, look } = D;
    try {
      await load3D();
      const scene = D.scene = new Atena3D.AtenaScene($("scene"), { onSelect: D.showNode, onHover: D.hoverNode,
        faceOptions: { color: FACE.color, style: FACE.style },
        onFaceReady: () => look.auto && AtenaAvatar.watchFps(() => scene.frames, look.info, (fps) => {
          console.warn(`3D a ${fps} fps: passo al nucleo leggero`);
          const swap = () => (D.busy || D.isSpeaking() ? setTimeout(swap, 3000) : location.reload());
          swap();
        }) });
      $("scene").style.display = "block";
      D.avatar = window.atenaAvatar = scene;
      window.atenaScene = scene;
      scene.setMode(D.mode);
      if (D.weather) scene.setWeather(D.weather);
      D.applyStage();
      D.refreshBrain(false);
    } catch (err) {
      console.warn("3D non disponibile, uso il nucleo leggero", err);
      look.mode = "light"; look.reason = "3D non disponibile su questo dispositivo";
      startLight();
    }
  }

  async function ensureBrain() {
    if (D.scene) return D.scene;
    await load3D();
    D.scene = D.scene || new Atena3D.AtenaScene($("scene"), { face: false, onSelect: D.showNode, onHover: D.hoverNode });
    window.atenaScene = D.scene;
    $("scene").style.display = "block";
    await D.refreshBrain(false);
    return D.scene;
  }

  D.startLook = () => {
    const look = D.look = window.atenaLook = AtenaAvatar.choose(D.FACE.avatar);
    console.info(`Aspetto: ${look.mode} (${look.reason})`, look.info);
    if (look.mode === "full") startFull(); else startLight();
  };

  D.setMode = (m) => {
    const { avatar, scene } = D;
    D.mode = m;
    document.body.classList.remove("face", "focus", "brain");
    document.body.classList.add(m);
    if (avatar && avatar !== scene) avatar.setMode(m);
    if (scene) scene.setMode(m);
    else if (m === "brain" && D.look.mode === "light") ensureBrain().then((s) => s.setMode(D.mode)).catch((err) => { console.warn(err); D.setMode("face"); });
    if (m === "brain") D.refreshBrain(false);
    else { $("inspector").classList.remove("show"); D.selectedId = null; if (scene) scene.brain.select(null); }
  };

  const PRESENCE = { large: 1.15, normal: 1, small: 0.82, mini: 0.7 };
  D.setPresence = (name) => {
    const k = PRESENCE[name] || 1;
    D.presence = name;
    for (const target of new Set([D.avatar, D.scene])) if (target && target.setPresence) target.setPresence(k);
  };

  D.applyStage = () => {
    const { avatar, scene, stageZone } = D;
    if (avatar && avatar.setStage) avatar.setStage(stageZone);
    if (scene && scene !== avatar && scene.setStage) scene.setStage(stageZone);
    const root = document.documentElement.style;
    if (stageZone) {
      root.setProperty("--av-x", `${stageZone.cx}px`);
      root.setProperty("--av-w", `${Math.max(260, stageZone.w)}px`);
      root.setProperty("--av-bottom", `${Math.max(96, window.innerHeight - (stageZone.y + stageZone.h) - 58)}px`);
    } else { ["--av-x", "--av-w", "--av-bottom"].forEach((k) => root.removeProperty(k)); }
  };
})();
