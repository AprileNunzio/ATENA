(() => {
  const HOLD_MS = 550, SLOP = 10, DETAIL_IDLE_MS = 90000;
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const safeImg = (u) => (/^https:\/\/[^\s"'<>]+$/i.test(String(u || "")) ? String(u) : "");
  const st = { down: null, timer: 0, menu: null, sheet: null, sheetTimer: 0, opened: 0 };

  function post(url, body) {
    return fetch(url, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-Atena-Request": "1" },
      body: JSON.stringify(body) }).then((r) => { if (!r.ok) throw new Error(`errore ${r.status}`); return r; });
  }

  const widgetOf = (el) => (el && el.closest ? el.closest(".desk > .widget") : null);
  const isFull = (w) => !!(w && w.classList.contains("fullscreen"));

  function fullscreen(key, on) {
    return post("/api/desk/fullscreen", { key, on }).catch((e) => console.warn("Schermo intero non riuscito:", e.message));
  }

  function close(key) {
    return post("/api/desk/close", { key }).catch((e) => console.warn("Chiusura non riuscita:", e.message));
  }

  function hideMenu() {
    if (st.menu) st.menu.remove();
    st.menu = null;
  }

  function menu(widget, x, y) {
    hideMenu();
    if (!widget) return;
    const key = widget.dataset.key, full = isFull(widget);
    const el = document.createElement("div");
    el.className = "wt-menu";
    el.innerHTML = `<div class="wt-menu-card" role="menu">
      <button type="button" data-wt="${full ? "shrink" : "grow"}">${full ? "Riduci" : "Ingrandisci"}</button>
      <button type="button" data-wt="close">Chiudi</button>
      <button type="button" data-wt="cancel">Annulla</button></div>`;
    document.body.appendChild(el);
    const card = el.firstElementChild, W = window.innerWidth, H = window.innerHeight;
    const r = card.getBoundingClientRect();
    card.style.left = `${Math.max(12, Math.min(W - r.width - 12, x - r.width / 2))}px`;
    card.style.top = `${Math.max(12, Math.min(H - r.height - 12, y - r.height / 2))}px`;
    el.addEventListener("click", (e) => {
      const b = e.target.closest("[data-wt]");
      if (b && b.dataset.wt === "grow") fullscreen(key, true);
      if (b && b.dataset.wt === "shrink") fullscreen(key, false);
      if (b && b.dataset.wt === "close") close(key);
      hideMenu();
    });
    st.menu = el;
    if (navigator.vibrate) navigator.vibrate(18);
  }

  function hideSheet() {
    clearTimeout(st.sheetTimer);
    if (st.sheet) st.sheet.remove();
    st.sheet = null;
  }

  function detail(raw) {
    let d;
    try { d = typeof raw === "string" ? JSON.parse(raw) : raw; } catch (e) { return; }
    if (!d || typeof d !== "object" || Date.now() - st.opened < 400) return;
    st.opened = Date.now();
    hideSheet(); hideMenu();
    const img = safeImg(d.image);
    const meta = [d.source, d.at].filter(Boolean).map(esc).join(" · ");
    const el = document.createElement("div");
    el.className = "wt-sheet";
    el.innerHTML = `<article class="wt-sheet-card">
      <button type="button" class="wt-x" data-wt="close" aria-label="Chiudi">✕</button>
      ${meta ? `<div class="wt-meta">${meta}</div>` : ""}
      <h1>${esc(String(d.title || "").slice(0, 200))}</h1>
      ${img ? `<img src="${esc(img)}" alt="" referrerpolicy="no-referrer">` : ""}
      ${d.text ? `<p>${esc(String(d.text).slice(0, 4000))}</p>` : ""}
      ${d.link ? `<div class="wt-link">${esc(String(d.link).slice(0, 200))}</div>` : ""}
      <div class="wt-actions">${d.text || d.title ? '<button type="button" data-wt="read">Leggimelo</button>' : ""}<button type="button" data-wt="close">Chiudi</button></div>
    </article>`;
    el.addEventListener("click", (e) => {
      const b = e.target.closest("[data-wt]");
      if (b && b.dataset.wt === "read" && window.AtenaDesk) window.AtenaDesk.ctx.speak(`${d.title || ""}. ${d.text || ""}`.slice(0, 1200));
      if ((b && b.dataset.wt === "close") || e.target === el) hideSheet();
    });
    document.body.appendChild(el);
    st.sheet = el;
    st.sheetTimer = setTimeout(hideSheet, DETAIL_IDLE_MS);
  }

  function cancelHold() {
    clearTimeout(st.timer);
    st.timer = 0;
  }

  function onDown(e) {
    if (e.button || st.menu && st.menu.contains(e.target) || st.sheet && st.sheet.contains(e.target)) return;
    const widget = widgetOf(e.target);
    if (!widget) { hideMenu(); return; }
    cancelHold();
    st.down = { x: e.clientX, y: e.clientY, target: e.target, widget, held: false, id: e.pointerId };
    st.timer = setTimeout(() => { st.down.held = true; menu(widget, st.down.x, st.down.y); }, HOLD_MS);
  }

  function onMove(e) {
    if (!st.down || e.pointerId !== st.down.id) return;
    if (Math.hypot(e.clientX - st.down.x, e.clientY - st.down.y) > SLOP) { cancelHold(); st.down.moved = true; }
  }

  function onUp(e) {
    const d = st.down;
    st.down = null;
    cancelHold();
    if (!d || e.pointerId !== d.id || d.held || d.moved) return;
    const item = d.target.closest && d.target.closest("[data-detail]");
    if (item && d.widget.contains(item)) detail(item.dataset.detail);
  }

  function onClick(e) {
    const item = e.target.closest && e.target.closest(".desk [data-detail]");
    if (item) detail(item.dataset.detail);
  }

  function exitButton() {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "wt-exit";
    b.textContent = "✕ Riduci";
    b.addEventListener("click", () => {
      const full = document.querySelector(".desk > .widget.fullscreen");
      if (full) fullscreen(full.dataset.key, false);
    });
    document.body.appendChild(b);
  }

  document.addEventListener("pointerdown", onDown, true);
  document.addEventListener("pointermove", onMove, true);
  document.addEventListener("pointerup", onUp, true);
  document.addEventListener("pointercancel", () => { st.down = null; cancelHold(); }, true);
  document.addEventListener("click", onClick);
  document.addEventListener("contextmenu", (e) => {
    const widget = widgetOf(e.target);
    if (!widget) return;
    e.preventDefault();
    menu(widget, e.clientX, e.clientY);
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") { hideMenu(); hideSheet(); } });
  if (document.body) exitButton(); else document.addEventListener("DOMContentLoaded", exitButton);

  window.AtenaTouch = { menu, detail, fullscreen, close, hideMenu, hideSheet, widgetOf, cancel: () => { cancelHold(); hideMenu(); } };
})();
