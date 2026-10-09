(() => {
  const A = window.AtenaAdmin;
  const ORIGIN = { x: 0, z: -11 };
  const ROLE_COLOR = { chat: 0x29e0ff, deep: 0xff8c3c, domotico: 0x3dffa8, ricercatore: 0xffc43d, studio: 0xa08cff, coder: 0xff7ac8, modello3d: 0x6ea8ff };
  const WALK = 3.2, COLS = 4;

  function room(world) {
    const T = window.THREE, g = new T.Group();
    const floor = new T.Mesh(new T.BoxGeometry(18, 0.2, 12), new T.MeshStandardMaterial({ color: 0x0a1a28, roughness: 0.8 }));
    floor.position.y = 0.1; g.add(floor);
    const glass = new T.MeshStandardMaterial({ color: 0x29e0ff, transparent: true, opacity: 0.07, side: T.DoubleSide, depthWrite: false });
    [[0, 1.6, -6, 18, 3.2, 0.05], [-9, 1.6, 0, 0.05, 3.2, 12], [9, 1.6, 0, 0.05, 3.2, 12]].forEach(([x, y, z, w, h, d]) => {
      const wall = new T.Mesh(new T.BoxGeometry(w, h, d), glass); wall.position.set(x, y, z); g.add(wall);
      const rim = new T.LineSegments(new T.EdgesGeometry(wall.geometry), new T.LineBasicMaterial({ color: 0x1d6f8f })); rim.position.copy(wall.position); g.add(rim);
    });
    const sofa = new T.Mesh(new T.BoxGeometry(4.5, 0.6, 1.2), new T.MeshStandardMaterial({ color: 0x2a1f4a, roughness: 0.7 }));
    sofa.position.set(-4, 0.5, 5.2); g.add(sofa);
    const tag = world.label("Ufficio degli agenti", { size: 30, border: "rgba(61,255,168,0.6)" }); tag.position.set(0, 4.2, -6); g.add(tag);
    const lounge = world.label("in attesa", { size: 22, border: "rgba(160,140,255,0.5)" }); lounge.position.set(-4, 1.9, 5.6); g.add(lounge);
    g.position.set(ORIGIN.x, 0, ORIGIN.z);
    world.scene.add(g);
    return g;
  }

  function desk(world, slot) {
    const T = window.THREE, g = new T.Group();
    const top = new T.Mesh(new T.BoxGeometry(2.2, 0.12, 1.1), new T.MeshStandardMaterial({ color: 0x173248, metalness: 0.5, roughness: 0.4 }));
    top.position.y = 0.9; g.add(top);
    const legs = new T.Mesh(new T.BoxGeometry(2.0, 0.8, 0.08), new T.MeshStandardMaterial({ color: 0x0c1c2a })); legs.position.set(0, 0.45, -0.45); g.add(legs);
    const screen = new T.Mesh(new T.BoxGeometry(1.1, 0.65, 0.05), world.glowMat(0x0b2a3c, 0.2)); screen.position.set(0, 1.35, -0.35); g.add(screen);
    const chair = new T.Mesh(new T.BoxGeometry(0.6, 0.12, 0.6), new T.MeshStandardMaterial({ color: 0x2a1f4a })); chair.position.set(0, 0.55, 0.75); g.add(chair);
    const x = ORIGIN.x - 5.4 + (slot % COLS) * 3.6, z = ORIGIN.z - 4.6 + Math.floor(slot / COLS) * 2.2;
    g.position.set(x, 0.2, z);
    world.scene.add(g);
    return { group: g, screen, seat: new window.THREE.Vector3(x, 0.2, z + 0.75) };
  }

  function person(world, color) {
    const T = window.THREE, g = new T.Group();
    const mat = world.glowMat(color, 0.35);
    const body = new T.Mesh(new T.CylinderGeometry(0.22, 0.3, 0.9, 12), mat); body.position.y = 0.75; g.add(body);
    const head = new T.Mesh(new T.SphereGeometry(0.22, 16, 12), world.glowMat(0xdff6ff, 0.25)); head.position.y = 1.42; g.add(head);
    const visor = new T.Mesh(new T.BoxGeometry(0.3, 0.07, 0.05), world.glowMat(color, 1.4)); visor.position.set(0, 1.45, 0.2); g.add(visor);
    world.scene.add(g);
    return { group: g, body, mat };
  }

  class Office {
    constructor(world) {
      this.world = world; this.agents = new Map(); room(world);
      world.tick((dt, t) => this.tick(dt, t));
    }

    lounge(i) {
      return new window.THREE.Vector3(ORIGIN.x - 7 + (i % 8) * 0.9, 0.2, ORIGIN.z + 3.4 + Math.floor(i / 8) * 0.9);
    }

    sync(desks) {
      desks.forEach((d, i) => {
        let a = this.agents.get(d.id);
        if (!a) {
          const spot = desk(this.world, i), p = person(this.world, ROLE_COLOR[d.role] || 0x29e0ff);
          const home = this.lounge(i);
          p.group.position.copy(home);
          const tag = this.world.label(d.label, { size: 22 }); tag.position.set(0, 2.05, 0); p.group.add(tag);
          tag.visible = false;
          a = { ...p, ...spot, home, tag, busy: false, sit: 0, bob: Math.random() * 6 };
          this.agents.set(d.id, a);
        }
        if (d.busy !== a.busy) {
          a.busy = d.busy;
          a.tag.visible = d.busy;
          a.screen.material.emissive.setHex(d.busy ? 0x29e0ff : 0x0b2a3c);
          a.screen.material.emissiveIntensity = d.busy ? 1.4 : 0.2;
          a.mat.emissiveIntensity = d.busy ? 0.9 : 0.35;
        }
      });
    }

    tick(dt, t) {
      for (const a of this.agents.values()) {
        const goal = a.busy ? a.seat : a.home, pos = a.group.position;
        const dx = goal.x - pos.x, dz = goal.z - pos.z, dist = Math.hypot(dx, dz);
        if (dist > 0.05) {
          const step = Math.min(dist, WALK * dt);
          pos.x += (dx / dist) * step; pos.z += (dz / dist) * step;
          a.group.rotation.y = Math.atan2(dx, dz);
          a.sit = Math.max(0, a.sit - dt * 3);
          pos.y = 0.2 + Math.abs(Math.sin(t * 9)) * 0.08;
        } else {
          a.sit = a.busy ? Math.min(1, a.sit + dt * 2.5) : Math.max(0, a.sit - dt * 3);
          a.group.rotation.y = a.busy ? Math.PI : a.group.rotation.y;
          pos.y = 0.2 - a.sit * 0.32 + (a.busy ? Math.sin(t * 6 + a.bob) * 0.015 : Math.sin(t * 1.5 + a.bob) * 0.02);
        }
        a.body.scale.y = 1 - a.sit * 0.25;
      }
    }
  }

  A.hubOffice = { Office };
})();
