(() => {
  "use strict";
  const SVG = "http://www.w3.org/2000/svg";
  const STATUS = { queued: "in coda", failed: "riproverò", waiting_disk: "serve spazio", done: "pronta" };
  const FAREWELL_MS = 6000;
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");

  const el = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  };

  function ring(size) {
    const box = el("span", "bgq-ring");
    const svg = document.createElementNS(SVG, "svg");
    svg.setAttribute("viewBox", `0 0 ${size} ${size}`);
    svg.setAttribute("aria-hidden", "true");
    const r = size / 2 - 2;
    const circ = 2 * Math.PI * r;
    for (const cls of ["track", "value"]) {
      const c = document.createElementNS(SVG, "circle");
      c.setAttribute("class", cls);
      c.setAttribute("cx", size / 2);
      c.setAttribute("cy", size / 2);
      c.setAttribute("r", r);
      if (cls === "value") {
        c.style.strokeDasharray = `${circ}`;
        c.style.strokeDashoffset = `${circ}`;
      }
      svg.append(c);
    }
    const label = el("b");
    const span = el("span");
    label.append(span);
    box.append(svg, label);
    return {
      box,
      set(pct, text) {
        const p = Math.max(0, Math.min(100, Number(pct) || 0));
        svg.lastChild.style.strokeDashoffset = `${circ * (1 - p / 100)}`;
        span.textContent = text ?? "";
      },
    };
  }

  function eta(seconds) {
    if (!Number.isFinite(seconds) || seconds <= 0) return "";
    if (seconds < 90) return "meno di 2 min";
    if (seconds < 3600) return `circa ${Math.round(seconds / 60)} min`;
    return `circa ${(seconds / 3600).toFixed(1).replace(".0", "")} ore`;
  }

  function mount() {
    const root = el("aside", "bgq");
    root.setAttribute("aria-live", "polite");
    root.setAttribute("aria-label", "Installazioni in background");

    const panel = el("section", "bgq-panel");
    panel.id = "bgq-panel";
    panel.hidden = true;
    const head = el("div", "bgq-head");
    const title = el("h3", null, "Installazioni in background");
    const sub = el("p");
    const bar = el("div", "bgq-bar");
    const fill = el("i");
    bar.append(fill);
    head.append(title, sub, bar);
    const list = el("ul", "bgq-list");
    const foot = el("div", "bgq-foot", "Atena è già pronta: queste parti si aggiungono da sole, senza riavvii.");
    panel.append(head, list, foot);

    const pill = el("button", "bgq-pill");
    pill.type = "button";
    pill.setAttribute("aria-expanded", "false");
    pill.setAttribute("aria-controls", panel.id);
    const main = ring(38);
    const text = el("span", "bgq-text");
    const line1 = el("strong");
    const line2 = el("small");
    text.append(line1, line2);
    pill.append(main.box, text);

    root.append(panel, pill);
    document.body.append(root);

    const toggle = (open) => {
      panel.hidden = !open;
      pill.setAttribute("aria-expanded", String(open));
    };
    pill.addEventListener("click", () => toggle(panel.hidden));
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") toggle(false); });
    document.addEventListener("pointerdown", (e) => { if (!root.contains(e.target)) toggle(false); }, { passive: true });

    const rows = new Map();
    const samples = [];
    let seenWork = false;
    let farewell = null;
    let gone = false;
    const lastStatus = new Map();

    function row(item) {
      let r = rows.get(item.id);
      if (!r) {
        const li = el("li", "bgq-item");
        const rg = ring(30);
        const name = el("div", "name");
        const strong = el("strong", null, item.title);
        const small = el("small");
        name.append(strong, small);
        const state = el("span", "state");
        li.append(rg.box, name, state);
        r = { li, rg, small, state };
        rows.set(item.id, r);
      }
      return r;
    }

    function speed(bg, totalGb) {
      const now = Date.now() / 1000;
      const doneGb = (totalGb * bg.progress) / 100;
      samples.push([now, doneGb]);
      while (samples.length > 2 && now - samples[0][0] > 300) samples.shift();
      const [t0, g0] = samples[0];
      const dt = now - t0;
      if (dt < 20 || doneGb <= g0) return "";
      return eta((totalGb - doneGb) / ((doneGb - g0) / dt));
    }

    function render(bg) {
      if (!bg || !Array.isArray(bg.items) || !bg.items.length) return;
      const finished = bg.finished && bg.items.every((i) => i.status === "done");
      if (!finished) seenWork = true;
      if (!seenWork) return;

      const totalGb = bg.items.reduce((a, i) => a + (Number(i.size_gb) || 0), 0);
      const current = bg.items.find((i) => i.status === "running");
      const pct = Math.round(Number(bg.progress) || 0);

      root.classList.toggle("paused", !!bg.paused);
      root.classList.toggle("done", finished);
      pill.classList.toggle("busy", !!current && !bg.paused && !reduced.matches);
      main.set(bg.progress, finished ? "✓" : `${pct}%`);
      fill.style.width = `${pct}%`;

      if (finished) {
        line1.textContent = "Atena è al completo";
        line2.textContent = "Tutte le parti sono installate";
        sub.textContent = `${bg.total} di ${bg.total} pronte`;
        if (!farewell) {
          farewell = setTimeout(() => { gone = true; toggle(false); root.classList.remove("show"); }, FAREWELL_MS);
        }
      } else {
        clearTimeout(farewell);
        farewell = null;
        gone = false;
        const left = speed(bg, totalGb);
        if (bg.paused) {
          line1.textContent = "Installazioni in pausa";
          line2.textContent = `${bg.done} di ${bg.total} pronte`;
        } else if (bg.conversation) {
          line1.textContent = current ? current.title : "In attesa";
          line2.textContent = "Riprendo quando finisci di parlare";
        } else {
          line1.textContent = current ? current.title : "Preparazione del prossimo componente";
          line2.textContent = [`${bg.done} di ${bg.total} pronte`, left].filter(Boolean).join(" · ");
        }
        sub.textContent = bg.paused
          ? `${bg.done} di ${bg.total} pronte · ${totalGb.toFixed(1)} GB in tutto · in pausa`
          : `${bg.done} di ${bg.total} pronte · ${totalGb.toFixed(1)} GB in tutto`;
      }

      bg.items.forEach((item, idx) => {
        const r = row(item);
        const before = lastStatus.get(item.id);
        r.li.className = `bgq-item ${item.status}`;
        if (before && before !== "done" && item.status === "done" && !reduced.matches) {
          r.li.classList.add("just-done");
        }
        r.rg.set(item.progress, item.status === "running" ? `${item.progress}` : "");
        r.small.textContent = item.status === "running" && item.detail ? item.detail
          : item.status === "waiting_disk" || item.status === "failed" ? (item.message || item.description)
          : `${Number(item.size_gb).toFixed(1)} GB · ${item.description}`;
        r.state.textContent = item.status === "running" ? `${item.progress}%` : (STATUS[item.status] || "");
        if (list.children[idx] !== r.li) list.insertBefore(r.li, list.children[idx] || null);
        lastStatus.set(item.id, item.status);
      });

      if (!gone) root.classList.add("show");
    }

    return render;
  }

  let render = null;
  const onState = (e) => {
    const bg = e.detail && e.detail.background;
    if (!bg) return;
    if (!render) {
      if (!document.body) return;
      render = mount();
    }
    render(bg);
  };
  addEventListener("atena:state", onState);
})();
