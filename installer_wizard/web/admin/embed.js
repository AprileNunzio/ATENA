(() => {
  let embedded = false;
  try { embedded = new URLSearchParams(location.search).get("embed") === "1" && window.top !== window.self; } catch { embedded = true; }
  if (embedded) document.documentElement.classList.add("embedded");
})();
