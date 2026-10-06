(() => {
  AtenaDesk.register("os_networks", {
    render(el, d, ctx) {
      const devs = Array.isArray(d.devices) ? d.devices.slice(0, 12) : [];
      const rows = devs.map((n) => {
        const ic = /bluetooth/i.test(String(n.name || "")) || n.type === "bluetooth" ? "bt" : n.secure ? "lock" : "unlock";
        return `<li class="wk-row ic${n.connected ? " on" : ""}">${ctx.icon(ic)}<span><b>${ctx.esc(n.name)}</b>${ctx.bar(n.signal)}</span>
          ${n.connected ? `<span class="wk-chip live">connesso</span>` : `<button class="wk-btn" type="button">Connetti</button>`}</li>`;
      }).join("");
      el.innerHTML = `${ctx.head({ icon: "wifi", label: "Reti e Bluetooth", title: devs.length ? `${devs.length} nelle vicinanze` : "" })}
        ${rows ? `<ul class="wk-list">${rows}</ul>` : `<div class="wk-empty">Nessun dispositivo nelle vicinanze</div>`}`;
    },
  });
})();
