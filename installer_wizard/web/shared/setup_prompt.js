(() => {
  "use strict";
  const show = () => {
    if (document.querySelector(".setup-cta")) return;
    const a = document.createElement("a");
    a.className = "setup-cta";
    a.href = "/setup";
    const icon = document.createElement("i");
    icon.textContent = "✦";
    const text = document.createElement("span");
    const strong = document.createElement("strong");
    strong.textContent = "Configura Atena";
    const small = document.createElement("small");
    small.textContent = "Bastano due minuti, anche mentre l'installazione continua";
    text.append(strong, small);
    a.append(icon, text);
    document.body.append(a);
  };
  fetch("/api/setup", { credentials: "same-origin", cache: "no-store" })
    .then((r) => (r.ok ? r.json() : null))
    .then((d) => { if (d && d.needed) show(); })
    .catch(() => {});
})();
