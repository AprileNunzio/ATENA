(() => {
  const PAGE_W = 1600, PAGE_H = 900;
  const FONT = '"Segoe Print","Bradley Hand","Comic Sans MS","Chalkboard SE",cursive', BG = "#12211b";
  const MONO = '"DejaVu Sans Mono","Cascadia Mono",Consolas,monospace', SANS = '"Segoe UI",Roboto,Arial,sans-serif';
  const COLORS = ["#f4f4f0", "#ffd166", "#ff4d6a", "#7cfc9a", "#29e0ff"];
  const WIDTHS = { s: 4, m: 9, l: 18 };
  const CALLOUT = { info: ["#29e0ff", "ℹ️"], tip: ["#7cfc9a", "💡"], warning: ["#ff4d6a", "⚠️"], definition: ["#ffd166", "📘"], formula: ["#c792ea", "∑"], example: ["#f4a261", "✏️"] };
  const SERIES = ["#29e0ff", "#ffd166", "#ff4d6a", "#7cfc9a", "#c792ea", "#f4a261", "#90e0ef", "#e9c46a"];
  const STRINGS = {
    it: { pen: "Penna", eraser: "Gomma", text: "Testo", color: "Colore", undo: "Annulla", clear: "Cancella lavagna", sure: "Sicuro?", save: "Salva",
      saveTitle: "Salva in memoria", load: "Carica", loadTitle: "Carica da memoria", aiTitle: "Attiva o disattiva la valutazione autonoma", aiOn: "🤖 AI: ON",
      aiOff: "🤖 AI: OFF", micOff: "🎤 Disattivato", micOn: "🎙️ Ascolto…", micTitle: "Parla con l'insegnante", prev: "Pagina precedente", next: "Pagina successiva",
      newPage: "Nuova pagina", delPage: "Elimina pagina", page: "Pag", pdfTitle: "Esporta in PDF", print: "Stampa", printTitle: "Stampa (laser, getto, 3D, incisore)",
      full: "Tutto schermo", close: "Chiudi", printHead: "🖨️ Stampa", searching: "Ricerca stampanti in corso…", noPrinters: "Nessuna stampante rilevata.",
      printersError: "Errore nel caricamento delle stampanti.", cancel: "Annulla", confirm: "Conferma stampa", sending: "Invio in corso…", sent: "Lavoro inviato.",
      error: "Errore", noMic: "Il browser non supporta il microfono in questa modalità.", thinking: "Sto pensando: ", boardName: "Nome della lavagna:",
      saved: "Lavagna salvata.", available: "Lavagne disponibili:", none: "Nessuna", loadName: "Nome della lavagna da caricare:", loaded: "Lavagna caricata.",
      aiEnabled: "Valutazione automatica attivata", aiDisabled: "Valutazione automatica disattivata", pdfStarted: "Download del PDF avviato…",
      types: { laser_2d: "Laser 2D", inkjet_2d: "Getto d'inchiostro", "3d": "Stampante 3D", engraver: "Incisore laser", virtual_pdf: "PDF" }, speech: "it-IT" },
    en: { pen: "Pen", eraser: "Eraser", text: "Text", color: "Colour", undo: "Undo", clear: "Clear board", sure: "Sure?", save: "Save",
      saveTitle: "Save to memory", load: "Load", loadTitle: "Load from memory", aiTitle: "Turn autonomous checking on or off", aiOn: "🤖 AI: ON",
      aiOff: "🤖 AI: OFF", micOff: "🎤 Off", micOn: "🎙️ Listening…", micTitle: "Talk to the teacher", prev: "Previous page", next: "Next page",
      newPage: "New page", delPage: "Delete page", page: "Page", pdfTitle: "Export to PDF", print: "Print", printTitle: "Print (laser, inkjet, 3D, engraver)",
      full: "Full screen", close: "Close", printHead: "🖨️ Print", searching: "Looking for printers…", noPrinters: "No printers found.",
      printersError: "Could not load the printers.", cancel: "Cancel", confirm: "Confirm print", sending: "Sending…", sent: "Job sent.",
      error: "Error", noMic: "This browser does not support the microphone here.", thinking: "Thinking: ", boardName: "Board name:",
      saved: "Board saved.", available: "Available boards:", none: "None", loadName: "Name of the board to load:", loaded: "Board loaded.",
      aiEnabled: "Autonomous checking on", aiDisabled: "Autonomous checking off", pdfStarted: "PDF download started…",
      types: { laser_2d: "Laser 2D", inkjet_2d: "Inkjet", "3d": "3D printer", engraver: "Laser engraver", virtual_pdf: "PDF" }, speech: "en-GB" },
  };
  const lang = () => {
    const code = (document.documentElement.lang || navigator.language || "it").slice(0, 2);
    return code in STRINGS ? code : "it";
  };
  const L = () => STRINGS[lang()];
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const post = (path, body) => fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) }).then((r) => r.json()).catch(() => ({}));
  const images = new Map();

  function image(it, onload) {
    let img = images.get(it.id);
    if (!img) {
      img = new Image();
      img.onload = onload;
      img.src = it.src;
      images.set(it.id, img);
    }
    return img.complete && img.naturalWidth ? img : null;
  }

  function roundRect(g, x, y, w, h, r) {
    g.beginPath();
    g.moveTo(x + r, y); g.arcTo(x + w, y, x + w, y + h, r); g.arcTo(x + w, y + h, x, y + h, r);
    g.arcTo(x, y + h, x, y, r); g.arcTo(x, y, x + w, y, r); g.closePath();
  }

  function niceStep(span) {
    const raw = span / 8, mag = Math.pow(10, Math.floor(Math.log10(raw))), n = raw / mag;
    return (n < 1.5 ? 1 : n < 3.5 ? 2 : n < 7.5 ? 5 : 10) * mag;
  }

  function drawPlot(g, it) {
    const pad = 46, x0 = it.x + pad, y0 = it.y + (it.title ? 40 : 14), w = it.w - pad - 14, h = it.h - (y0 - it.y) - 34;
    const sx = (v) => x0 + ((v - it.xmin) / (it.xmax - it.xmin)) * w, sy = (v) => y0 + h - ((v - it.ymin) / (it.ymax - it.ymin)) * h;
    g.save();
    g.fillStyle = "rgba(0,0,0,.25)"; g.fillRect(it.x, it.y, it.w, it.h);
    if (it.title) { g.fillStyle = "#ffd166"; g.font = `26px ${SANS}`; g.textBaseline = "top"; g.fillText(it.title, it.x + 12, it.y + 8); }
    g.font = `14px ${MONO}`; g.lineWidth = 1;
    for (const [lo, hi, axis] of [[it.xmin, it.xmax, "x"], [it.ymin, it.ymax, "y"]]) {
      const step = niceStep(hi - lo);
      for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) {
        g.strokeStyle = "rgba(255,255,255,.08)"; g.beginPath();
        if (axis === "x") { g.moveTo(sx(v), y0); g.lineTo(sx(v), y0 + h); } else { g.moveTo(x0, sy(v)); g.lineTo(x0 + w, sy(v)); }
        g.stroke();
        g.fillStyle = "rgba(255,255,255,.55)";
        const label = Math.abs(v) < 1e-9 ? "0" : +v.toPrecision(3) + "";
        if (axis === "x") { g.textBaseline = "top"; g.fillText(label, sx(v) - 8, y0 + h + 6); } else { g.textBaseline = "middle"; g.fillText(label, it.x + 4, sy(v)); }
      }
    }
    g.strokeStyle = "rgba(255,255,255,.6)"; g.lineWidth = 2; g.beginPath();
    if (it.ymin <= 0 && it.ymax >= 0) { g.moveTo(x0, sy(0)); g.lineTo(x0 + w, sy(0)); }
    if (it.xmin <= 0 && it.xmax >= 0) { g.moveTo(sx(0), y0); g.lineTo(sx(0), y0 + h); }
    g.stroke();
    g.beginPath(); g.rect(x0, y0, w, h); g.clip();
    it.series.forEach((s) => {
      g.strokeStyle = s.color; g.lineWidth = 3; g.beginPath();
      let pen = false;
      for (const [px, py] of s.points) {
        if (py === null || py === undefined) { pen = false; continue; }
        pen ? g.lineTo(sx(px), sy(py)) : g.moveTo(sx(px), sy(py));
        pen = true;
      }
      g.stroke();
    });
    g.restore();
    g.font = `18px ${MONO}`; g.textBaseline = "top";
    it.series.forEach((s, i) => { g.fillStyle = s.color; g.fillText(s.label, x0 + 10, y0 + 8 + i * 24); });
  }

  function drawChart(g, it) {
    const top = it.y + (it.title ? 44 : 14), h = it.h - (top - it.y) - 40, max = Math.max(...it.values.map(Math.abs), 1e-9);
    g.save();
    g.fillStyle = "rgba(0,0,0,.25)"; g.fillRect(it.x, it.y, it.w, it.h);
    if (it.title) { g.fillStyle = "#ffd166"; g.font = `26px ${SANS}`; g.textBaseline = "top"; g.fillText(it.title, it.x + 12, it.y + 8); }
    g.font = `16px ${SANS}`;
    if (it.kind === "pie") {
      const total = it.values.reduce((a, b) => a + b, 0), cx = it.x + it.h / 2 + 10, cy = top + h / 2, r = Math.min(h / 2, it.w / 3);
      let a = -Math.PI / 2;
      it.values.forEach((v, i) => {
        const da = (v / total) * Math.PI * 2;
        g.fillStyle = SERIES[i % SERIES.length]; g.beginPath(); g.moveTo(cx, cy); g.arc(cx, cy, r, a, a + da); g.closePath(); g.fill();
        g.textBaseline = "middle";
        g.fillRect(cx + r + 30, top + 9 + i * 26, 14, 14);
        g.fillStyle = "#f4f4f0";
        g.fillText(`${it.labels[i]} ${Math.round((v / total) * 100)}%`, cx + r + 52, top + 16 + i * 26);
        a += da;
      });
    } else {
      const left = it.x + 20, w = it.w - 40, n = it.values.length, slot = w / n, base = top + h;
      g.strokeStyle = "rgba(255,255,255,.5)"; g.beginPath(); g.moveTo(left, base); g.lineTo(left + w, base); g.stroke();
      const ys = it.values.map((v) => base - (Math.max(v, 0) / max) * (h - 24));
      it.values.forEach((v, i) => {
        const cx = left + slot * i + slot / 2;
        if (it.kind === "bar") { g.fillStyle = SERIES[i % SERIES.length]; g.fillRect(cx - slot * 0.32, ys[i], slot * 0.64, base - ys[i]); }
        g.fillStyle = "#f4f4f0"; g.textAlign = "center"; g.textBaseline = "bottom"; g.fillText(+v.toPrecision(4) + "", cx, ys[i] - 4);
        g.textBaseline = "top"; g.fillText(it.labels[i], cx, base + 8); g.textAlign = "left";
      });
      if (it.kind === "line") {
        g.strokeStyle = SERIES[0]; g.lineWidth = 3; g.beginPath();
        ys.forEach((y, i) => { const cx = left + slot * i + slot / 2; i ? g.lineTo(cx, y) : g.moveTo(cx, y); });
        g.stroke();
      }
    }
    g.restore();
  }

  function drawTable(g, it) {
    const cols = Math.max(it.header.length, ...it.rows.map((r) => r.length), 1), rowH = it.size * 1.6, w = it.w / cols;
    let y = it.y;
    g.save();
    g.textBaseline = "middle";
    if (it.title) { g.fillStyle = "#ffd166"; g.font = `${it.size + 4}px ${SANS}`; g.fillText(it.title, it.x, y + it.size * 0.7); y += it.size * 1.4; }
    const rows = it.header.length ? [it.header, ...it.rows] : it.rows;
    rows.forEach((row, r) => {
      const head = r === 0 && it.header.length;
      g.fillStyle = head ? "rgba(41,224,255,.18)" : r % 2 ? "rgba(255,255,255,.04)" : "rgba(0,0,0,.15)";
      g.fillRect(it.x, y, it.w, rowH);
      g.font = `${head ? "bold " : ""}${it.size}px ${SANS}`;
      g.fillStyle = head ? "#29e0ff" : "#f4f4f0";
      row.forEach((cell, c) => { g.save(); g.beginPath(); g.rect(it.x + c * w, y, w - 6, rowH); g.clip(); g.fillText(cell, it.x + c * w + 10, y + rowH / 2); g.restore(); });
      y += rowH;
    });
    g.strokeStyle = "rgba(255,255,255,.2)"; g.strokeRect(it.x, it.y + (it.title ? it.size * 1.4 : 0), it.w, y - it.y - (it.title ? it.size * 1.4 : 0));
    g.restore();
  }

  function drawCallout(g, it, appear) {
    const [ink, icon] = CALLOUT[it.kind] || CALLOUT.info;
    g.save();
    g.globalAlpha = appear;
    g.translate(it.x + it.w / 2, it.y + it.h / 2); g.scale(0.92 + 0.08 * appear, 0.92 + 0.08 * appear); g.translate(-(it.x + it.w / 2), -(it.y + it.h / 2));
    roundRect(g, it.x, it.y, it.w, it.h, 16);
    g.fillStyle = "rgba(6,20,26,.92)"; g.fill();
    g.strokeStyle = ink; g.lineWidth = 3; g.stroke();
    g.fillStyle = ink; g.fillRect(it.x, it.y + 12, 6, it.h - 24);
    g.textBaseline = "top"; g.font = `bold 28px ${SANS}`; g.fillText(`${icon}  ${it.title}`, it.x + 22, it.y + 14);
    g.font = `${it.size}px ${SANS}`; g.fillStyle = "#eef9ff";
    it.lines.forEach((line, i) => g.fillText(line, it.x + 22, it.y + 56 + i * it.size * 1.35));
    g.restore();
  }

  function drawMark(g, it) {
    const x = Math.min(it.x1, it.x2), y = Math.min(it.y1, it.y2), w = Math.abs(it.x2 - it.x1), h = Math.abs(it.y2 - it.y1);
    g.save();
    g.strokeStyle = g.fillStyle = it.color; g.lineWidth = it.width;
    if (it.style === "highlight") { g.globalAlpha = 0.28; g.fillRect(x - 6, y - 2, w + 12, h + 4); }
    else if (it.style === "underline") { g.beginPath(); g.moveTo(x, y + h + 4); g.lineTo(x + w, y + h + 4); g.stroke(); }
    else if (it.style === "wavy") { g.beginPath(); for (let i = 0; i <= w; i += 10) { const yy = y + h + 4 + (i % 20 ? 4 : -4); i ? g.lineTo(x + i, yy) : g.moveTo(x, yy); } g.stroke(); }
    else if (it.style === "circle") { g.beginPath(); g.ellipse(x + w / 2, y + h / 2, w / 2 + 18, h / 2 + 14, -0.04, 0, Math.PI * 2); g.stroke(); }
    else if (it.style === "box") { roundRect(g, x - 10, y - 8, w + 20, h + 16, 8); g.stroke(); }
    else if (it.style === "strike") { g.beginPath(); g.moveTo(x, y + h / 2); g.lineTo(x + w, y + h / 2); g.stroke(); }
    g.restore();
  }

  function paint(g, items, view, reveal, appear, onImage) {
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.clearRect(0, 0, g.canvas.width, g.canvas.height);
    g.setTransform(view.k, 0, 0, view.k, view.ox, view.oy);
    g.lineCap = g.lineJoin = "round";
    for (const it of items) {
      g.globalCompositeOperation = it.type === "erase" ? "destination-out" : "source-over";
      g.strokeStyle = g.fillStyle = it.color || "#f4f4f0";
      g.lineWidth = it.width || 4;
      if (it.type === "stroke" || it.type === "erase") {
        g.beginPath();
        it.points.forEach((p, i) => (i ? g.lineTo(p[0], p[1]) : g.moveTo(p[0], p[1])));
        if (it.points.length === 1) g.lineTo(it.points[0][0] + 0.1, it.points[0][1]);
        g.stroke();
      } else if (it.type === "text") {
        g.font = `${it.size}px ${FONT}`;
        g.textBaseline = "top";
        const shown = reveal && reveal(it) < it.text.length ? it.text.slice(0, Math.floor(reveal(it))) : it.text;
        g.fillText(shown, it.x, it.y);
      } else if (it.type === "line" || it.type === "arrow") {
        g.beginPath(); g.moveTo(it.x1, it.y1); g.lineTo(it.x2, it.y2); g.stroke();
        if (it.type === "arrow") {
          const a = Math.atan2(it.y2 - it.y1, it.x2 - it.x1), n = 12 + it.width * 2;
          g.beginPath(); g.moveTo(it.x2, it.y2);
          g.lineTo(it.x2 - n * Math.cos(a - 0.45), it.y2 - n * Math.sin(a - 0.45));
          g.moveTo(it.x2, it.y2);
          g.lineTo(it.x2 - n * Math.cos(a + 0.45), it.y2 - n * Math.sin(a + 0.45));
          g.stroke();
        }
      } else if (it.type === "rect") {
        g.strokeRect(Math.min(it.x1, it.x2), Math.min(it.y1, it.y2), Math.abs(it.x2 - it.x1), Math.abs(it.y2 - it.y1));
      } else if (it.type === "ellipse") {
        g.beginPath();
        g.ellipse((it.x1 + it.x2) / 2, (it.y1 + it.y2) / 2, Math.abs(it.x2 - it.x1) / 2 || 1, Math.abs(it.y2 - it.y1) / 2 || 1, 0, 0, Math.PI * 2);
        g.stroke();
      } else if (it.type === "mark") {
        drawMark(g, it);
      } else if (it.type === "callout") {
        drawCallout(g, it, appear ? appear(it) : 1);
      } else if (it.type === "formula") {
        g.font = `${it.size}px ${MONO}`; g.textBaseline = "top";
        let left = it.x;
        if (it.label) { g.fillStyle = "#ffd166"; g.fillText(it.label, it.x, it.y + ((it.lines.length - 1) * it.size * 1.25) / 2); left += g.measureText(it.label + "  ").width; }
        g.fillStyle = it.color;
        it.lines.forEach((line, i) => g.fillText(line, left, it.y + i * it.size * 1.25));
      } else if (it.type === "image") {
        const img = image(it, onImage);
        g.save(); g.globalAlpha = appear ? appear(it) : 1;
        if (img) {
          const ratio = Math.min(it.w / img.naturalWidth, it.h / img.naturalHeight), w = img.naturalWidth * ratio, h = img.naturalHeight * ratio;
          g.drawImage(img, it.x, it.y, w, h);
          g.strokeStyle = "rgba(255,255,255,.35)"; g.lineWidth = 2; g.strokeRect(it.x, it.y, w, h);
          if (it.caption) { g.fillStyle = "rgba(255,255,255,.7)"; g.font = `18px ${SANS}`; g.textBaseline = "top"; g.fillText(it.caption, it.x, it.y + h + 8); }
        } else { g.strokeStyle = "rgba(255,255,255,.2)"; g.strokeRect(it.x, it.y, it.w, it.h); }
        g.restore();
      } else if (it.type === "plot") {
        drawPlot(g, it);
      } else if (it.type === "chart") {
        drawChart(g, it);
      } else if (it.type === "table") {
        drawTable(g, it);
      }
    }
    g.globalCompositeOperation = "source-over";
  }

  function mount(el, ctx) {
    if (el._lv) el._lv.stop();
    document.body.classList.add("desk-whiteboard");
    const t = L();

    el.innerHTML = `<div class="lv">
      <div class="lv-bar">
        <button data-t="pen" class="on" title="${esc(t.pen)}">✏️</button>
        <button data-t="eraser" title="${esc(t.eraser)}">🧽</button>
        <button data-t="text" title="${esc(t.text)}">T</button>
        <span class="lv-sep"></span>
        ${COLORS.map((c) => `<button data-c="${c}" class="lv-dot" style="--c:${c}" title="${esc(t.color)}"></button>`).join("")}
        <span class="lv-sep"></span>
        <button data-w="s">·</button>
        <button data-w="m" class="on">●</button>
        <button data-w="l">⬤</button>
        <span class="lv-sep"></span>
        <button data-a="undo" title="${esc(t.undo)}">↶</button>
        <button data-a="clear" title="${esc(t.clear)}">🗑</button>
        <span class="lv-sep"></span>
        <button data-a="save" title="${esc(t.saveTitle)}">💾 ${esc(t.save)}</button>
        <button data-a="load" title="${esc(t.loadTitle)}">📁 ${esc(t.load)}</button>
        <span class="lv-sep"></span>
        <button data-a="ai-toggle" class="lv-ai-btn active" title="${esc(t.aiTitle)}">${esc(t.aiOn)}</button>
        <button id="lv-mic-btn" title="${esc(t.micTitle)}">${esc(t.micOff)}</button>
        <span class="lv-sep"></span>
        <div class="lv-page-ctrl">
          <button data-a="prev-page" title="${esc(t.prev)}">◀</button>
          <span class="lv-page-badge" id="lv-page-num">${esc(t.page)} 1 / 1</span>
          <button data-a="next-page" title="${esc(t.next)}">▶</button>
          <button data-a="new-page" title="${esc(t.newPage)}">+</button>
          <button data-a="del-page" title="${esc(t.delPage)}" style="display:none">🗑 ${esc(t.page)}</button>
        </div>
        <span class="lv-sep"></span>
        <button data-a="pdf" title="${esc(t.pdfTitle)}">📄 PDF</button>
        <button data-a="print" title="${esc(t.printTitle)}">🖨️ ${esc(t.print)}</button>
        <span class="lv-fill"></span>
        <button data-a="full" title="${esc(t.full)}">⤢</button>
        <button data-a="close" title="${esc(t.close)}">✕</button>
      </div>
      <div class="lv-stage">
        <canvas class="lv-canvas"></canvas>
        <input class="lv-input" maxlength="200" hidden>
      </div>
      <div class="lv-atena"><div class="lv-orb"></div><div class="lv-says" hidden></div></div>
      <div class="lv-modal-mask" style="display:none">
        <div class="lv-modal">
          <div class="lv-modal-head"><h3>${esc(t.printHead)}</h3><button data-m="close" class="lv-modal-x">✕</button></div>
          <div class="lv-modal-body" id="lv-printer-list"><div class="lv-modal-note">${esc(t.searching)}</div></div>
          <div class="lv-modal-foot">
            <button data-m="close" class="lv-btn-plain">${esc(t.cancel)}</button>
            <button data-m="submit" class="lv-btn-action">${esc(t.confirm)}</button>
          </div>
        </div>
      </div>
      <div class="lv-toast" style="display:none" id="lv-toast"></div>
    </div>`;

    const stage = el.querySelector(".lv-stage"), canvas = el.querySelector("canvas"), g = canvas.getContext("2d");
    const input = el.querySelector(".lv-input"), says = el.querySelector(".lv-says"), orb = el.querySelector(".lv-orb");
    const pageBadge = el.querySelector("#lv-page-num"), delPageBtn = el.querySelector('[data-a="del-page"]');
    const aiBtn = el.querySelector('[data-a="ai-toggle"]');
    const modalMask = el.querySelector(".lv-modal-mask"), printerList = el.querySelector("#lv-printer-list");
    const toast = el.querySelector("#lv-toast");

    const st = {
      items: [], rev: 0, tool: "pen", ink: COLORS[0], width: WIDTHS.m,
      seen: new Map(), first: true, view: { k: 1, ox: 0, oy: 0 }, drawing: null, said: "",
      timers: [], raf: 0, page: 0, pages: 1, ai_enabled: true,
      evalTimer: 0, snapTimer: 0, armed: 0, selectedPrinter: "pdf_export"
    };
    const key = "lavagna";
    const ANIMATED = new Set(["text", "callout", "image"]);

    const showToast = (msg) => {
      toast.textContent = msg;
      toast.style.display = "block";
      setTimeout(() => { toast.style.display = "none"; }, 4000);
    };

    const reveal = (it) => {
      if (it.by !== "atena" || !st.seen.has(it.id)) return it.text ? it.text.length : 0;
      return (performance.now() - st.seen.get(it.id)) * 0.045;
    };
    const appear = (it) => (st.seen.has(it.id) ? Math.min(1, (performance.now() - st.seen.get(it.id)) / 450) : 1);
    const animating = () => st.items.some((i) => i.by === "atena" && st.seen.has(i.id) &&
      ((i.type === "text" && reveal(i) < i.text.length) || (i.type !== "text" && appear(i) < 1)));

    const redraw = () => {
      const live = st.drawing ? [...st.items, st.drawing] : st.items;
      paint(g, live, st.view, reveal, appear, redraw);
      const busy = animating();
      orb.classList.toggle("busy", busy);
      cancelAnimationFrame(st.raf);
      if (busy) st.raf = requestAnimationFrame(redraw);
    };

    const fit = () => {
      const r = stage.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
      const W = r.width || window.innerWidth, H = r.height || window.innerHeight;
      const k = Math.min(W / PAGE_W, H / PAGE_H);
      st.css = { k, ox: (W - PAGE_W * k) / 2, oy: (H - PAGE_H * k) / 2 };
      st.view = { k: k * dpr, ox: st.css.ox * dpr, oy: st.css.oy * dpr };
      canvas.style.width = `${W}px`;
      canvas.style.height = `${H}px`;
      canvas.width = Math.round(W * dpr);
      canvas.height = Math.round(H * dpr);
      redraw();
    };

    const point = (e) => {
      const r = canvas.getBoundingClientRect(), c = st.css || { k: 1, ox: 0, oy: 0 };
      const x = (e.clientX - r.left - c.ox) / c.k, y = (e.clientY - r.top - c.oy) / c.k;
      return [Math.round(Math.max(0, Math.min(PAGE_W, x)) * 10) / 10, Math.round(Math.max(0, Math.min(PAGE_H, y)) * 10) / 10];
    };

    const takeSnapshot = () => {
      const c = document.createElement("canvas");
      c.width = 1280; c.height = 720;
      const s = c.getContext("2d");
      s.fillStyle = BG; s.fillRect(0, 0, 1280, 720);
      const layer = document.createElement("canvas");
      layer.width = 1280; layer.height = 720;
      paint(layer.getContext("2d"), st.items, { k: 0.8, ox: 0, oy: 0 }, null, null, () => {});
      s.drawImage(layer, 0, 0);
      return post("/api/board/snapshot", { image: c.toDataURL("image/jpeg", 0.78) });
    };

    const scheduleSnapshot = () => {
      clearTimeout(st.snapTimer);
      st.snapTimer = setTimeout(takeSnapshot, 1200);
    };

    const triggerAutonomousEval = () => {
      if (!st.ai_enabled) return;
      clearTimeout(st.evalTimer);
      st.evalTimer = setTimeout(() => {
        takeSnapshot().then(() => post("/api/board/auto_evaluate")).then((res) => {
          if (res && res.evaluated) poll();
        });
      }, 3500);
    };

    const updateAiButton = () => {
      aiBtn.classList.toggle("active", st.ai_enabled);
      aiBtn.classList.toggle("inactive", !st.ai_enabled);
      aiBtn.textContent = st.ai_enabled ? t.aiOn : t.aiOff;
    };

    const updatePageBadge = () => {
      pageBadge.textContent = `${t.page} ${st.page + 1} / ${Math.max(1, st.pages)}`;
      delPageBtn.style.display = st.pages > 1 ? "inline-flex" : "none";
    };

    const apply = (data) => {
      if (data.same) return;
      const fresh = new Set(data.items.map((i) => i.id));
      for (const it of data.items) {
        if (!st.first && it.by === "atena" && ANIMATED.has(it.type) && !st.seen.has(it.id) && !st.items.some((o) => o.id === it.id)) {
          st.seen.set(it.id, performance.now());
        }
      }
      for (const id of [...st.seen.keys()]) if (!fresh.has(id)) st.seen.delete(id);
      for (const id of [...images.keys()]) if (!fresh.has(id)) images.delete(id);
      st.first = false;
      st.items = data.items;
      st.rev = data.rev;
      st.page = Number(data.page || 0);
      st.pages = Number(data.pages || 1);
      st.ai_enabled = data.ai_enabled !== undefined ? Boolean(data.ai_enabled) : st.ai_enabled;
      updateAiButton();
      updatePageBadge();
      if (data.says && data.says !== st.said) {
        st.said = data.says;
        says.textContent = data.says;
        says.hidden = false;
        clearTimeout(st.timers[0]);
        st.timers[0] = setTimeout(() => { says.hidden = true; }, 25000);
      }
      redraw();
      scheduleSnapshot();
    };

    const poll = () => fetch(`/api/board?rev=${st.rev}`).then((r) => r.json()).then(apply).catch(() => {});
    poll();
    st.timers.push(setInterval(poll, 900));

    canvas.addEventListener("pointerdown", (e) => {
      if (e.button > 0) return;
      const p = point(e);
      if (st.tool === "text") {
        input.hidden = false;
        input.style.left = `${(e.clientX - stage.getBoundingClientRect().left)}px`;
        input.style.top = `${(e.clientY - stage.getBoundingClientRect().top)}px`;
        input.dataset.x = p[0]; input.dataset.y = p[1];
        input.value = "";
        setTimeout(() => input.focus(), 0);
        return;
      }
      canvas.setPointerCapture(e.pointerId);
      st.drawing = { type: st.tool === "eraser" ? "erase" : "stroke", points: [p], color: st.ink, width: st.tool === "eraser" ? st.width * 3 : st.width };
      redraw();
    });

    canvas.addEventListener("pointermove", (e) => {
      if (!st.drawing) return;
      const p = point(e), last = st.drawing.points[st.drawing.points.length - 1];
      if (Math.hypot(p[0] - last[0], p[1] - last[1]) < 1.5) return;
      st.drawing.points.push(p);
      redraw();
    });

    const finish = () => {
      const d = st.drawing;
      st.drawing = null;
      if (!d) return;
      st.items = [...st.items, { ...d, by: "user", id: -Date.now() }];
      redraw();
      post("/api/board/stroke", { points: d.points, color: d.color, width: d.width, tool: d.type === "erase" ? "eraser" : "pen" }).then(poll);
      scheduleSnapshot();
      triggerAutonomousEval();
    };

    canvas.addEventListener("pointerup", finish);
    canvas.addEventListener("pointercancel", finish);

    input.addEventListener("keydown", (e) => {
      if (e.key === "Escape") input.hidden = true;
      if (e.key === "Enter" && input.value.trim()) {
        post("/api/board/text", { text: input.value, x: Number(input.dataset.x), y: Number(input.dataset.y), size: 44, color: st.ink }).then(poll);
        input.hidden = true;
        triggerAutonomousEval();
      }
    });

    const openPrinterModal = () => {
      modalMask.style.display = "flex";
      fetch("/api/board/printers").then((r) => r.json()).then((d) => {
        const prs = d.printers || [];
        if (d.default) st.selectedPrinter = d.default;
        if (!prs.length) {
          printerList.innerHTML = `<div class="lv-modal-note">${esc(t.noPrinters)}</div>`;
          return;
        }
        printerList.innerHTML = prs.map((p) => {
          const badgeClass = { laser_2d: "laser", inkjet_2d: "ink", "3d": "threed", engraver: "engraver" }[p.type] || "";
          return `<div class="lv-printer-row ${p.id === st.selectedPrinter ? "selected" : ""}" data-pid="${esc(p.id)}">
            <div class="lv-printer-info">
              <span class="lv-printer-name">${esc(p.name)}</span>
              <span class="lv-printer-meta">${esc(p.address || p.connection)} · ${esc(p.status || "")}</span>
            </div>
            <span class="lv-printer-badge ${badgeClass}">${esc(t.types[p.type] || p.type)}</span>
          </div>`;
        }).join("");
      }).catch(() => {
        printerList.innerHTML = `<div class="lv-modal-note lv-err">${esc(t.printersError)}</div>`;
      });
    };

    printerList.addEventListener("click", (e) => {
      const row = e.target.closest(".lv-printer-row");
      if (!row) return;
      printerList.querySelectorAll(".lv-printer-row").forEach((r) => r.classList.remove("selected"));
      row.classList.add("selected");
      st.selectedPrinter = row.dataset.pid;
    });

    modalMask.addEventListener("click", (e) => {
      const btn = e.target.closest("button");
      if (!btn) return;
      if (btn.dataset.m === "close") {
        modalMask.style.display = "none";
      } else if (btn.dataset.m === "submit") {
        btn.disabled = true;
        btn.textContent = t.sending;
        post("/api/board/print", { printer_id: st.selectedPrinter }).then((res) => {
          modalMask.style.display = "none";
          btn.disabled = false;
          btn.textContent = t.confirm;
          showToast((res && res.job && res.job.message) || (res && res.detail ? `${t.error}: ${res.detail}` : t.sent));
        });
      }
    });

    el.querySelector(".lv-bar").addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (!b) return;
      const pick = (attr, value) => { el.querySelectorAll(`[data-${attr}]`).forEach((x) => x.classList.toggle("on", x === b)); return value; };
      if (b.id === "lv-mic-btn") {
        if (!window.SpeechRecognition && !window.webkitSpeechRecognition) {
          showToast(t.noMic);
          return;
        }
        if (st.listening) {
          st.recognition.stop();
          return;
        }
        const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
        st.recognition = new SpeechRec();
        st.recognition.lang = t.speech;
        st.recognition.continuous = false;
        st.recognition.interimResults = false;
        st.recognition.onstart = () => { st.listening = true; b.textContent = t.micOn; b.style.color = "#ff4d6a"; };
        st.recognition.onend = () => { st.listening = false; b.textContent = t.micOff; b.style.color = ""; };
        st.recognition.onresult = (event) => {
          const transcript = event.results[0][0].transcript;
          showToast(t.thinking + transcript);
          takeSnapshot().then(() => post("/api/board/ask", { question: transcript })).then(poll);
        };
        st.recognition.start();
        return;
      }
      if (b.dataset.t) {
        st.tool = pick("t", b.dataset.t);
        input.hidden = true;
        canvas.style.cursor = st.tool === "text" ? "text" : "crosshair";
      } else if (b.dataset.c) {
        st.ink = b.dataset.c;
        if (st.tool === "eraser") st.tool = "pen";
        el.querySelectorAll("[data-t]").forEach((x) => x.classList.toggle("on", x.dataset.t === st.tool));
      } else if (b.dataset.w) {
        st.width = WIDTHS[pick("w", b.dataset.w)];
      } else if (b.dataset.a === "undo") {
        post("/api/board/undo").then(poll);
      } else if (b.dataset.a === "clear") {
        if (Date.now() - st.armed > 3000) {
          st.armed = Date.now();
          b.textContent = t.sure;
          setTimeout(() => { b.textContent = "🗑"; }, 3000);
          return;
        }
        st.armed = 0;
        b.textContent = "🗑";
        post("/api/board/clear").then(poll);
      } else if (b.dataset.a === "save") {
        const name = prompt(t.boardName);
        if (name) post("/api/board/save", { name }).then(() => { showToast(t.saved); poll(); });
      } else if (b.dataset.a === "load") {
        fetch("/api/board/list").then((r) => r.json()).then((res) => {
          const names = res.boards || [];
          const name = prompt(`${t.available}\n${names.length ? names.join("\n") : t.none}\n\n${t.loadName}`);
          if (name) post("/api/board/load", { name }).then(() => { showToast(t.loaded); poll(); });
        });
      } else if (b.dataset.a === "ai-toggle") {
        post("/api/board/ai/toggle").then((res) => {
          if (res && res.ai_enabled !== undefined) st.ai_enabled = res.ai_enabled;
          updateAiButton();
          showToast(st.ai_enabled ? t.aiEnabled : t.aiDisabled);
        });
      } else if (b.dataset.a === "prev-page") {
        if (st.page > 0) post("/api/board/page/switch", { page: st.page - 1 }).then(poll);
      } else if (b.dataset.a === "next-page") {
        if (st.page + 1 < st.pages) post("/api/board/page/switch", { page: st.page + 1 }).then(poll);
      } else if (b.dataset.a === "new-page") {
        post("/api/board/page/new").then(poll);
      } else if (b.dataset.a === "del-page") {
        post("/api/board/page/delete", { page: st.page }).then(poll);
      } else if (b.dataset.a === "pdf") {
        const link = document.createElement("a");
        link.href = "/api/board/pdf";
        link.download = "atena_whiteboard.pdf";
        document.body.appendChild(link);
        link.click();
        link.remove();
        showToast(t.pdfStarted);
      } else if (b.dataset.a === "print") {
        openPrinterModal();
      } else if (b.dataset.a === "full") {
        post("/api/desk/fullscreen", { key, on: !el.closest(".widget").classList.contains("fullscreen") });
      } else if (b.dataset.a === "close") {
        post("/api/desk/close", { key });
      }
    });

    const watch = new ResizeObserver(fit);
    watch.observe(stage);
    canvas.style.cursor = "crosshair";
    el._lv = {
      stop() {
        document.body.classList.remove("desk-whiteboard");
        watch.disconnect();
        st.timers.forEach((tm) => { clearInterval(tm); clearTimeout(tm); });
        clearTimeout(st.snapTimer);
        clearTimeout(st.evalTimer);
        if (st.recognition) st.recognition.stop();
        cancelAnimationFrame(st.raf);
      }
    };
    fit();
  }

  AtenaDesk.register("lavagna", { render: mount, update() {}, destroy(el) { if (el._lv) el._lv.stop(); } });
})();
