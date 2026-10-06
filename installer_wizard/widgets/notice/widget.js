(() => {
  const NAMES = new Set(["alert", "info", "error", "check", "bell", "clock", "timer", "calendar", "home", "door", "light", "user", "users", "contact", "music", "camera", "shield", "lock", "wifi", "bt", "lan", "server", "phone", "mail", "chat", "gift", "star", "car", "bolt", "drop", "fire", "therm", "download", "refresh", "sparkle", "book", "file", "pin"]);
  const EMOJI = [
    [/🎂|🎁|🎉|🎈/u, "gift"], [/⚠|❗|‼/u, "alert"], [/🚨|🔥/u, "fire"], [/📱|☎|📞/u, "phone"], [/✉|📧|📨/u, "mail"],
    [/💬/u, "chat"], [/📅|🗓/u, "calendar"], [/⏰|⏱|🕐/u, "clock"], [/💡/u, "light"], [/🔒|🔐/u, "lock"], [/🛡/u, "shield"],
    [/📶|🛜/u, "wifi"], [/🖥|💻|🖧/u, "server"], [/🚗|🚙/u, "car"], [/⚡|🔋/u, "bolt"], [/✅|✔/u, "check"], [/ℹ/u, "info"],
    [/👤|🧑|👩|👨/u, "user"], [/🏠|🏡/u, "home"], [/⭐|🌟/u, "star"], [/🎵|🎶/u, "music"],
  ];
  const pick = (v) => {
    const s = String(v || "");
    if (NAMES.has(s)) return s;
    const hit = EMOJI.find(([re]) => re.test(s));
    return hit ? hit[1] : "bell";
  };
  AtenaDesk.register("notice", {
    render(el, d, ctx) {
      const warn = d.level === "warn";
      el.innerHTML = `${ctx.head({ label: warn ? "Attenzione" : "Avviso" })}
        <div class="no-row"><span class="no-ic">${ctx.icon(pick(d.icon))}</span><div>
          <div class="wk-title">${ctx.esc(String(d.title || "").slice(0, 120))}</div>
          ${d.text ? `<div class="wk-sub">${ctx.esc(String(d.text).slice(0, 300))}</div>` : ""}</div></div>`;
      if (el.parentNode) {
        el.parentNode.classList.toggle("no-warn", warn);
        el.parentNode.classList.toggle("tone-amber", warn);
      }
    },
  });
})();
