(() => {
  function draw(el, d, ctx) {
    const items = Array.isArray(d.items) ? d.items.slice(0, 30) : [];
    el.innerHTML = `<div class="fg">
      ${d.title ? `<div class="fg-title">${ctx.esc(d.title)}</div>` : ""}
      ${d.value !== undefined && d.value !== "" ? `<div class="fg-value">${ctx.esc(d.value)}<small>${ctx.esc(d.unit || "")}</small></div>` : ""}
      ${d.label ? `<div class="fg-label">${ctx.esc(d.label)}</div>` : ""}
      ${d.text ? `<p class="fg-text">${ctx.esc(d.text)}</p>` : ""}
      ${items.length ? `<ul class="fg-list">${items.map((i) => `<li>${ctx.esc(typeof i === "object" ? Object.values(i).join(" · ") : i)}</li>`).join("")}</ul>` : ""}
    </div>`;
  }

  AtenaDesk.register("__ID__", { render: draw, update: draw, destroy() {} });
})();
