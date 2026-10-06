(() => {
  const KEEP = new Set(["B", "STRONG", "I", "EM", "U", "S", "MARK", "SMALL", "SUB", "SUP", "CODE", "BR", "P", "UL", "OL", "LI", "BLOCKQUOTE", "H1", "H2", "H3", "H4", "PRE", "SPAN", "DIV"]);
  const DROP = new Set(["SCRIPT", "STYLE", "TEMPLATE", "IFRAME", "OBJECT", "EMBED", "SVG", "MATH", "NOSCRIPT", "TITLE", "HEAD"]);
  const copy = (src, dst, depth) => {
    for (const n of src.childNodes) {
      if (n.nodeType === Node.TEXT_NODE) { dst.append(document.createTextNode(n.nodeValue)); continue; }
      if (n.nodeType !== Node.ELEMENT_NODE || DROP.has(n.tagName)) continue;
      if (depth > 12) { dst.append(document.createTextNode(n.textContent)); continue; }
      if (KEEP.has(n.tagName)) {
        const e = document.createElement(n.tagName === "H1" || n.tagName === "H2" ? "h3" : n.tagName.toLowerCase());
        copy(n, e, depth + 1);
        dst.append(e);
      } else copy(n, dst, depth + 1);
    }
  };
  const rich = (target, html) => {
    const doc = new DOMParser().parseFromString(String(html).slice(0, 4000), "text/html");
    copy(doc.body, target, 0);
  };
  AtenaDesk.register("text_short", {
    render(el, d) {
      el.innerHTML = `<div class="wk-text tx-short"></div>`;
      if (d.content) {
        const box = el.firstChild;
        box.textContent = "";
        rich(box, d.content);
      }
    },
  });
})();
