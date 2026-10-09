(() => {
  const safeUrl = (u) => {
    const s = String(u || "").trim();
    return /^(https?:\/\/|\/(?!\/)|data:image\/)/i.test(s) ? s : "";
  };
  AtenaDesk.register("brief", {
    render(el, d, ctx) {
      const src = safeUrl(d.image && d.image.src);
      const image = src
        ? `<figure class="br-fig"><img src="${ctx.esc(src)}" alt="${ctx.esc(d.title || "")}">${d.image.credit ? `<figcaption>${ctx.esc(String(d.image.credit).slice(0, 120))}</figcaption>` : ""}</figure>`
        : "";
      const details = Array.isArray(d.details) ? d.details : [];
      const lines = (Array.isArray(d.lines) ? d.lines : []).slice(0, 8).map((l, i) => (details[i] && ctx.detail
        ? `<li class="wk-tap"${ctx.detail(details[i])}>${ctx.esc(l)}</li>` : `<li>${ctx.esc(l)}</li>`)).join("");
      el.innerHTML = `${ctx.head({ icon: "pin", label: "Scheda", title: d.title ? String(d.title).slice(0, 80) : "" })}
        ${image}${lines ? `<ul class="br-lines">${lines}</ul>` : ""}`;
    },
  });
})();
