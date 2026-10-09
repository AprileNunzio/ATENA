(() => {
  const A = window.AtenaAdmin;
  const SPEED = 0.16, LEAVE = 4.5, MAX_TRUCKS = 3;

  function model(world, color) {
    const T = window.THREE, g = new T.Group();
    const body = new T.MeshStandardMaterial({ color: 0x16324a, metalness: 0.6, roughness: 0.35 });
    const cab = new T.Mesh(new T.BoxGeometry(1.1, 1.0, 1.2), body); cab.position.set(1.15, 0.75, 0); g.add(cab);
    const glass = new T.Mesh(new T.BoxGeometry(0.05, 0.45, 1.0), world.glowMat(0x29e0ff, 0.8)); glass.position.set(1.71, 0.95, 0); g.add(glass);
    const cargo = new T.Mesh(new T.BoxGeometry(2.0, 1.3, 1.3), world.glowMat(color, 0.25)); cargo.position.set(-0.45, 0.95, 0); g.add(cargo);
    const edges = new T.LineSegments(new T.EdgesGeometry(cargo.geometry), new T.LineBasicMaterial({ color })); edges.position.copy(cargo.position); g.add(edges);
    const wheel = new T.CylinderGeometry(0.28, 0.28, 0.22, 16);
    const wheels = [];
    [[1.15, 0.65], [1.15, -0.65], [-0.9, 0.65], [-0.9, -0.65]].forEach(([x, z]) => {
      const w = new T.Mesh(wheel, new T.MeshStandardMaterial({ color: 0x050a10 })); w.rotation.x = Math.PI / 2; w.position.set(x, 0.28, z); g.add(w); wheels.push(w);
    });
    const light = new T.PointLight(0x29e0ff, 0.9, 6); light.position.set(2, 0.8, 0); g.add(light);
    g.scale.setScalar(0.9);
    return { group: g, cargo, wheels };
  }

  class Fleet {
    constructor(world, stations) {
      this.world = world; this.count = stations.length; this.trucks = new Map();
      world.tick((dt, t) => this.tick(dt, t));
    }

    target(j) { return Math.min(1, j.reached / (this.count - 1)); }

    spawn(j) {
      const w = this.world, color = w.colors.AMBER;
      const m = model(w, color);
      const tag = w.label(`❝ ${j.query.slice(0, 60)}${j.query.length > 60 ? "…" : ""} ❞`, { size: 26, border: "rgba(255,196,61,0.7)" });
      tag.position.set(0, 2.6, 0); m.group.add(tag);
      w.scene.add(m.group);
      const truck = { j, ...m, tag, u: 0, goal: this.target(j), done: 0, gone: false };
      this.trucks.set(j.id, truck);
      return truck;
    }

    sync(list) {
      const seen = new Set();
      list.slice(0, MAX_TRUCKS).forEach((j) => {
        seen.add(j.id);
        const t = this.trucks.get(j.id) || this.spawn(j);
        t.j = j; t.goal = this.target(j);
        if (j.state !== "running" && !t.done) {
          t.done = performance.now() / 1000;
          t.cargo.material.emissive.setHex(j.failed ? 0xff4d6a : this.world.colors.GREEN);
          t.cargo.material.emissiveIntensity = 0.9;
        }
      });
      for (const [id, t] of this.trucks) if (!seen.has(id) && !t.done) t.done = performance.now() / 1000;
    }

    tick(dt, now) {
      const curve = this.world.curve;
      for (const [id, t] of this.trucks) {
        const goal = t.done && now - t.done > LEAVE * 0.4 ? 1 : t.goal;
        const step = Math.sign(goal - t.u) * Math.min(Math.abs(goal - t.u), SPEED * dt * (goal > t.u + 0.2 ? 2.2 : 1));
        t.u = Math.max(0, Math.min(1, t.u + step));
        const p = curve.getPointAt(t.u), q = curve.getPointAt(Math.min(1, t.u + 0.01));
        t.group.position.set(p.x, 0.1 + (Math.abs(step) > 1e-5 ? Math.sin(now * 18) * 0.03 : 0), p.z);
        t.group.rotation.y = -Math.atan2(q.z - p.z, q.x - p.x);
        t.wheels.forEach((w) => { w.rotation.y += step * 60; });
        this.world.gates.forEach((g, i) => {
          const near = Math.abs(i / (this.count - 1) - t.u) < 0.04;
          g.beam.material.emissiveIntensity = near ? 2.2 : 0.9;
        });
        if (t.done && now - t.done > LEAVE) {
          t.group.traverse((o) => { if (o.material) { o.material.transparent = true; o.material.opacity = Math.max(0, (o.material.opacity ?? 1) - dt); } });
          if (now - t.done > LEAVE + 1.2) { this.world.scene.remove(t.group); this.trucks.delete(id); }
        }
      }
    }
  }

  A.hubFleet = { Fleet };
})();
