(() => {
  const ext = (name) => (String(name).split(".").pop() || "").toLowerCase();
  const base = (path) => String(path).split("/").pop();
  const ICON = { docx: "doc", odt: "doc", xlsx: "chart", ods: "chart", pptx: "image", odp: "image", pdf: "file" };
  const safeUrl = (u) => {
    const s = String(u || "").trim();
    return /^(https?:\/\/|\/(?!\/))/i.test(s) ? s : "";
  };

  function office(el, d, ctx) {
    const id = encodeURIComponent(String(d.id ?? ""));
    const files = (Array.isArray(d.files) ? d.files.slice(0, 20) : []).map((f, i) => `<li class="wk-row ic">${ctx.icon(ICON[ext(f)] || "file")}
        <a class="dv-link" href="/api/documents/${id}/file/${i}" target="_blank" rel="noopener noreferrer"><b>${ctx.esc(base(f))}</b></a>
        <span class="wk-val">${ctx.esc(ext(f))}</span></li>`).join("");
    const errs = Array.isArray(d.errors) ? d.errors.slice(0, 6) : [];
    const errors = errs.length ? `<div class="dv-err"><span>Non riusciti</span> <span>${errs.map(ctx.esc).join("; ")}</span></div>` : "";
    const preview = d.preview ? `<div class="wk-media dv-prev"><iframe class="dv-frame" src="/api/documents/${id}/preview.pdf#view=FitH&toolbar=0"></iframe></div>` : "";
    el.innerHTML = `${ctx.head({ icon: "doc", label: d.kind === "progetto" ? "Progetto" : "Documento", title: d.title || "Documento" })}
      ${d.summary ? `<div class="wk-sub">${ctx.esc(d.summary)}</div>` : ""}
      <div class="dv-body${preview ? " with-preview" : ""}"><div><ul class="wk-list">${files}</ul>${errors}
        <div class="wk-faint dv-where"><span>Cartella condivisa</span> › 01 <span>Documenti</span>${d.project ? ` › ${ctx.esc(base(d.project))}` : ""}</div></div>${preview}</div>`;
  }

  AtenaDesk.register("document_viewer", {
    render(el, d, ctx) {
      if (d.type === "office") return office(el, d, ctx);
      const url = safeUrl(d.url);
      const content = url ? `<div class="wk-media dv-prev"><iframe class="dv-frame" src="${ctx.esc(url)}"></iframe></div>`
        : `<div class="wk-empty"><span>Anteprima non disponibile per questo formato</span> (${ctx.esc(d.type || "file")})</div>`;
      el.innerHTML = `${ctx.head({ icon: "doc", label: "Visualizzatore", title: d.title || "", chip: d.type || "file" })}${content}`;
    },
  });
})();
