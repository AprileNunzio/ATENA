(() => {
  const D = window.AtenaDisplay, { $, fmt } = D;
  const esc = fmt.esc;
  const state = { snap: null, pick: null, sel: null, timer: null, seen: new Set(), forced: false, sig: "" };

  const secs = (ms) => `${(ms / 1000).toFixed(ms < 10000 ? 1 : 0)} s`;
  const tone = (rgb) => `--c:${rgb}`;
  const TONES = {
    input: "41,224,255",
    laws: "255,196,61",
    cache: "61,255,168",
    router: "160,140,255",
    classifier: "160,140,255",
    planner: "255,140,60",
    decision: "80,180,255",
    pool: "80,180,255",
    agent: "61,255,168",
    reasoning: "255,140,60",
    tool: "61,255,168",
    jury: "255,77,106",
    voter: "255,196,61",
    dag_node: "160,140,255",
    attempt: "255,140,60",
    system2: "255,140,60",
    skill: "255,140,60",
    answer: "61,255,168",
    error: "255,77,106",
    flow: "41,224,255",
    call: "80,180,255",
    fallback: "255,196,61",
    back: "255,77,106"
  };

  const ICONS = {
    input: "◎",
    laws: "⚖",
    cache: "⚡",
    router: "⤹",
    classifier: "🏷",
    planner: "🗺",
    decision: "◆",
    pool: "👥",
    agent: "🤖",
    reasoning: "🧠",
    tool: "⚙",
    jury: "🛡",
    voter: "🗳",
    dag_node: "⬡",
    attempt: "↻",
    system2: "∞",
    skill: "✦",
    answer: "∑",
    error: "✕"
  };

  function journeys() {
    return (state.snap && state.snap.journeys) || [];
  }

  function current() {
    const list = journeys();
    return list.find((j) => j.id === state.pick) || list[0] || null;
  }

  // Costruisce la matrice a colonne posizionali a partire dall'albero di dipendenze dei nodi
  function layout(j) {
    const nodes = j.nodes || [];
    const edges = j.edges || [];
    if (!nodes.length) return { cols: [], edges: [] };

    const byId = new Map(nodes.map((n) => [n.i, n]));
    const kids = new Map();
    nodes.forEach((n) => {
      if (n.p !== null && n.p !== undefined) {
        if (!kids.has(n.p)) kids.set(n.p, []);
        kids.get(n.p).push(n.i);
      }
    });

    // Calcolo della colonna per profondità topologica
    const colOf = new Map();
    function computeCol(id, depth) {
      colOf.set(id, Math.max(colOf.get(id) || 0, depth));
      (kids.get(id) || []).forEach((kid) => computeCol(kid, depth + 1));
    }
    const roots = nodes.filter((n) => n.p === null || n.p === undefined);
    roots.forEach((r) => computeCol(r.i, 0));

    // Nodi terminali (answer o error) sempre all'ultima colonna
    let maxCol = Math.max(...Array.from(colOf.values()), 0);
    nodes.forEach((n) => {
      if (n.k === "answer" || n.k === "error") {
        colOf.set(n.i, maxCol + 1);
      }
    });
    maxCol = Math.max(...Array.from(colOf.values()), 0);

    const cols = [];
    for (let c = 0; c <= maxCol; c++) {
      cols.push(nodes.filter((n) => (colOf.get(n.i) || 0) === c));
    }

    return { cols, edges };
  }

  function nodeHtml(n, jId) {
    const key = `${jId}:${n.i}`;
    const icon = ICONS[n.k] || "•";
    const statusClass = n.s === "running" ? "live" : n.s === "fail" ? "bad" : n.s === "skip" ? "wait" : "ok";
    const duration = n.b !== null && n.b !== undefined ? `${(n.b - (n.a || 0)).toFixed(2)}s` : "in corso";

    return `<div class="fnode ${n.k} ${statusClass} ${state.sel === key ? "sel" : ""}" data-k="${key}">
      <div class="fnode-top">
        <span class="fnode-ico">${icon}</span>
        <div>
          <div class="fnode-kind">${esc(n.k.toUpperCase())}</div>
          <div class="fnode-name">${esc(n.n)}</div>
        </div>
        <span class="fnode-time">${duration}</span>
      </div>
      ${n.d ? `<div class="fnode-sub">${esc(n.d)}</div>` : ""}
    </div>`;
  }

  function drawLines(stage, edges, jId) {
    const svg = stage.querySelector(".flow-svg");
    if (!svg) return;
    const els = {};
    stage.querySelectorAll("[data-k]").forEach((el) => { els[el.dataset.k] = el; });
    const sr = stage.getBoundingClientRect();
    svg.setAttribute("width", stage.scrollWidth);
    svg.setAttribute("height", stage.scrollHeight);

    let out = "";
    edges.forEach(([u, v, kind, label]) => {
      const ea = els[`${jId}:${u}`], eb = els[`${jId}:${v}`];
      if (!ea || !eb) return;
      const ra = ea.getBoundingClientRect(), rb = eb.getBoundingClientRect();

      const isBack = kind === "back" || rb.left <= ra.left;
      let x1, y1, x2, y2, d;

      if (isBack) {
        // Linea curva di ritorno (loop indietro sopra o sotto il nodo)
        x1 = ra.left + (ra.width / 2) - sr.left;
        y1 = ra.top - sr.top;
        x2 = rb.left + (rb.width / 2) - sr.left;
        y2 = rb.top - sr.top;
        const topH = Math.min(y1, y2) - 40;
        d = `M ${x1} ${y1} C ${x1} ${topH}, ${x2} ${topH}, ${x2} ${y2}`;
      } else {
        x1 = ra.right - sr.left;
        y1 = ra.top + ra.height / 2 - sr.top;
        x2 = rb.left - sr.left;
        y2 = rb.top + rb.height / 2 - sr.top;
        const mx = x1 + (x2 - x1) / 2;
        d = `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`;
      }

      const rgb = TONES[kind] || TONES.flow;
      const dash = kind === "fallback" || kind === "back";
      out += `<path class="flow-line ${dash ? "dash" : ""}" style="${tone(rgb)}" d="${d}"/>`;

      if (label) {
        const midX = (x1 + x2) / 2;
        const midY = (y1 + y2) / 2 - (isBack ? 25 : 8);
        out += `<text x="${midX}" y="${midY}" fill="rgba(${rgb}, 0.9)" font-size="9" font-family="monospace" text-anchor="middle">${esc(label)}</text>`;
      }

      // Animazione particella di luce lungo il tragitto
      out += `<circle r="${isBack ? 3.5 : 2.8}" class="flow-dot" style="${tone(rgb)}">
        <animateMotion dur="${isBack ? '1.8s' : '2.4s'}" repeatCount="indefinite" path="${d}"/>
      </circle>`;
    });

    svg.innerHTML = out;
  }

  function renderDetail(j) {
    const box = $("flow-detail");
    if (!state.sel || !j) { box.classList.remove("show"); return; }
    const nodeId = parseInt(state.sel.split(":")[1], 10);
    const node = (j.nodes || []).find((n) => n.i === nodeId);
    if (!node) { box.classList.remove("show"); return; }

    const statusBadge = node.s === "ok" ? "✓ SUCCESSO" : node.s === "fail" ? "✕ FALLITO / RIPROVA" : node.s === "running" ? "⌁ IN CORSO" : "SALTO";
    box.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
        <span style="font-weight:bold; color:var(--cyan); letter-spacing:0.1em;">${esc(node.k.toUpperCase())} · ${esc(node.n)}</span>
        <span style="font-size:11px; padding:2px 8px; border-radius:4px; background:rgba(255,255,255,0.08); font-family:monospace;">${statusBadge}</span>
      </div>
      <div style="font-size:12px; line-height:1.6; color:#cbd5e1; word-break:break-word; white-space:pre-wrap;">${esc(node.d || "Nessun dettaglio aggiuntivo disponibile per questo passaggio.")}</div>
      <div style="margin-top:10px; font-size:10px; color:var(--text-faint); font-family:monospace;">
        Inizio: +${(node.a || 0).toFixed(3)}s | Concluso: ${node.b !== null ? `+${node.b.toFixed(3)}s` : 'attivo'}
      </div>
    `;
    box.classList.add("show");
  }

  function render() {
    const j = current();
    const tabs = $("flow-tabs"), canvas = $("flow-stage"), bar = $("flow-bar");
    const list = journeys();

    tabs.innerHTML = list.map((x) => `
      <button class="flow-tab ${x.id === (j && j.id) ? "sel" : ""} ${x.state === "running" ? "live" : x.state === "failed" ? "failed" : ""}" data-id="${x.id}">
        ${esc(x.query || "Domanda")} · ${x.state === "running" ? "in corso" : secs((x.elapsed || 0) * 1000)}
      </button>
    `).join("");

    if (!j) {
      canvas.innerHTML = `
        <div class="flow-empty">
          <b>Nessun percorso registrato finora.</b><br>
          Fai una domanda ad Atena sul dock: il grafo si costruirà in tempo reale dalla A alla Z,<br>
          mostrando la memoria, le leggi, i giudizi di consenso, i cicli ReAct e i ritorni.
        </div>`;
      bar.innerHTML = `<span><i class="dot"></i>In attesa di richieste</span><span></span><span></span>`;
      $("flow-detail").classList.remove("show");
      return;
    }

    const { cols, edges } = layout(j);
    const colsHtml = cols.map((colNodes, idx) => {
      if (!colNodes.length) return "";
      return `<div class="flow-col">
        <div class="flow-col-title">Fase ${idx + 1}</div>
        ${colNodes.map((n) => nodeHtml(n, j.id)).join("")}
      </div>`;
    }).join("");

    canvas.innerHTML = `<svg class="flow-svg"></svg>${colsHtml}`;
    requestAnimationFrame(() => drawLines(canvas, edges, j.id));
    renderDetail(j);

    const live = j.state === "running";
    bar.innerHTML = `
      <span><i class="dot ${live ? "live" : j.state}"></i>Stato: <b>${live ? "in esecuzione" : j.state === "failed" ? "fallito" : "concluso"}</b></span>
      <span>Agente: <b>${esc(j.agent || "Dispatcher")}</b></span>
      <span>Passi: <b>${(j.nodes || []).length}</b></span>
      <span>Tempo: <b>${secs((j.elapsed || 0) * 1000)}</b></span>
    `;
  }

  async function poll() {
    if (D.mode !== "flow") return;
    try {
      const r = await fetch("/api/brain/journey", { cache: "no-store" });
      if (!r.ok) return;
      const data = await r.json();
      const sig = `${data.seq}|${state.pick}|${state.sel}`;
      state.snap = data;
      if (sig !== state.sig) { state.sig = sig; render(); }
    } catch (err) { return; }
  }

  function loop() {
    clearTimeout(state.timer);
    if (D.mode !== "flow") return;
    state.timer = setTimeout(async () => { await poll(); loop(); }, 800);
  }

  function enter() { state.sig = ""; poll().then(loop); }

  const base = D.setMode;
  D.setMode = (m) => {
    if (D.mode === "flow" && (m === "face" || m === "focus") && !state.forced) return;
    document.body.classList.remove("flow");
    if (m === "flow") {
      base("face");
      document.body.classList.remove("face");
      document.body.classList.add("flow");
      D.mode = "flow";
      enter();
      return;
    }
    clearTimeout(state.timer);
    base(m);
  };

  D.exitFlow = () => { state.forced = true; try { D.setMode("face"); } finally { state.forced = false; } };

  D.startFlow = () => {
    const btn = $("btn-flow");
    if (btn) btn.addEventListener("click", () => {
      D.lastInteraction = Date.now();
      if (D.mode === "flow") D.exitFlow(); else D.setMode("flow");
    });
    const backBtn = $("flow-back");
    if (backBtn) backBtn.addEventListener("click", D.exitFlow);

    $("flow-tabs").addEventListener("click", (ev) => {
      const b = ev.target.closest(".flow-tab"); if (!b) return;
      state.pick = b.dataset.id; state.sel = null; state.sig = ""; render();
    });

    $("flow-stage").addEventListener("click", (ev) => {
      const n = ev.target.closest(".fnode"); if (!n) return;
      state.sel = state.sel === n.dataset.k ? null : n.dataset.k;
      renderDetail(current());
      $("flow-stage").querySelectorAll(".fnode").forEach((el) => {
        el.classList.toggle("sel", el.dataset.k === state.sel);
      });
    });

    addEventListener("keydown", (ev) => { if (ev.key === "Escape" && D.mode === "flow") D.exitFlow(); });
    addEventListener("resize", () => { if (D.mode === "flow") { state.sig = ""; render(); } });
  };
})();
