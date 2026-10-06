(() => {
  const DEVICE_KEY = "atena-device";
  const ID_OK = /^[A-Za-z0-9_-]{6,40}$/;
  const REPORT_EVERY = 30000, POLICY_EVERY = 120000;
  const STOP = Symbol("stop");
  const st = { policy: null, tier: "full", costs: {}, applied: false, reportFails: 0 };

  const randomId = () => Array.from(crypto.getRandomValues(new Uint8Array(12)), (b) => b.toString(16).padStart(2, "0")).join("");
  function deviceId() {
    try {
      let v = localStorage.getItem(DEVICE_KEY);
      if (!ID_OK.test(v || "")) { v = randomId(); localStorage.setItem(DEVICE_KEY, v); }
      return v;
    } catch (err) { return randomId(); }
  }
  const DEVICE = deviceId();

  function setTier(tier) {
    if (tier === st.tier && st.applied) return;
    st.tier = tier;
    st.applied = true;
    document.body.classList.toggle("tier-reduced", tier === "reduced");
    document.body.classList.toggle("tier-minimal", tier === "minimal");
    if (window.atenaPerf) {
      if (tier !== "full") window.atenaPerf.lite(`governatore: ${tier}`);
      else if (window.atenaPerf.relax) window.atenaPerf.relax();
    }
    window.dispatchEvent(new CustomEvent("atena-tier", { detail: tier }));
  }

  function adopt(policy) {
    const before = st.policy;
    st.policy = policy;
    setTier(policy.enabled ? policy.tier : "full");
    if (!before || before.max_active !== policy.max_active || before.max_ambient !== policy.max_ambient) {
      window.dispatchEvent(new CustomEvent("atena-policy", { detail: policy }));
    }
  }

  async function pull() {
    try {
      const r = await fetch(`/api/governor/policy?device=${DEVICE}`, { cache: "no-store" });
      if (r.ok) adopt(await r.json());
    } catch (err) { console.warn("Politica delle risorse non letta", err); }
  }

  function limit(list) {
    const p = st.policy;
    if (!p || !p.enabled) return list;
    const must = list.filter((i) => i.takeover || i.intent || i.pos);
    const rest = list.filter((i) => !(i.takeover || i.intent || i.pos));
    const keep = new Set([...must, ...rest.slice(0, Math.max(0, Math.max(1, p.max_active) - must.length))]);
    return list.filter((i) => keep.has(i));
  }

  function cost(id, ms, nodes = 0, mount = false) {
    const key = String(id).toLowerCase().replace(/[^a-z0-9_-]/g, "-").slice(0, 40) || "x";
    const c = st.costs[key] || (st.costs[key] = { id: key, ms: 0, mounts: 0, nodes: 0 });
    c.ms += ms;
    if (mount) c.mounts++;
    if (nodes) c.nodes = Math.max(c.nodes, nodes);
  }

  function measure(id, fn, el, mount = false) {
    const t0 = performance.now();
    try { return fn(); } finally {
      cost(id, performance.now() - t0, el ? el.getElementsByTagName("*").length : 0, mount);
    }
  }

  function frameGap(kind) {
    const base = kind === "ambient" ? 33 : 16;
    if (st.tier === "minimal") return kind === "ambient" ? Infinity : 66;
    return st.tier === "reduced" ? base * 2 : base;
  }

  function poll(name, fn, ms, max = ms * 8) {
    let timer = 0, delay = ms, stopped = false;
    const slow = () => (st.tier === "minimal" ? 4 : st.tier === "reduced" ? 2 : 1);
    const next = () => { if (!stopped) timer = setTimeout(run, Math.min(max, delay) * slow()); };
    const run = async () => {
      if (stopped) return;
      if (document.hidden) { next(); return; }
      const t0 = performance.now();
      try {
        const out = await fn();
        if (out === STOP) { stopped = true; return; }
        delay = ms;
      } catch (err) { delay = Math.min(max, delay * 2); }
      cost(`poll-${name}`, performance.now() - t0);
      next();
    };
    next();
    return () => { stopped = true; clearTimeout(timer); };
  }

  async function report() {
    const p = st.policy;
    if (!p || !p.report || document.hidden || st.reportFails > 5) return;
    const perf = (window.atenaPerf && window.atenaPerf.stats) || { fps: 0, p95: 0, longMs: 0 };
    const widgets = Object.values(st.costs).sort((a, b) => b.ms - a.ms).slice(0, 30)
      .map((c) => ({ id: c.id, ms: Math.round(c.ms), mounts: c.mounts, nodes: c.nodes }));
    st.costs = {};
    const active = window.AtenaDesk ? window.AtenaDesk.active.length : 0;
    try {
      const r = await fetch("/api/governor/report", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ device: DEVICE, fps: perf.fps, p95: perf.p95, longtask_ms: perf.longMs, active, visible: true, widgets }) });
      if (!r.ok) { st.reportFails++; return; }
      st.reportFails = 0;
      adopt(await r.json());
    } catch (err) { st.reportFails++; }
  }

  pull();
  setInterval(pull, POLICY_EVERY);
  setInterval(report, REPORT_EVERY);
  window.atenaGovernor = {
    limit, measure, cost, poll, frameGap, STOP, device: DEVICE, refresh: pull, report,
    get tier() { return st.tier; },
    get policy() { return st.policy; },
  };
})();
