(() => {
  const A = window.AtenaAdmin, { $ } = A;
  const VPN = (window.AtenaVpn = window.AtenaVpn || {});
  const split = (text) => String(text || "").split(/[\s,]+/).filter(Boolean);

  function showKind() {
    const kind = $("vpn-form").elements.kind.value;
    document.querySelectorAll("#vpn-form .vpn-kind").forEach((box) => { box.hidden = box.dataset.kind !== kind; });
    const tunnel = /^(wireguard:client|openvpn|ipsec)/.test(kind);
    $("vpn-form").elements.kill_switch.closest("label").hidden = !tunnel;
  }

  function body(f) {
    const v = (n) => (f.elements[n].value || "").trim();
    const [kind, role] = f.elements.kind.value.split(":");
    const data = {
      name: v("name"), kind, role, autostart: f.elements.autostart.checked, kill_switch: f.elements.kill_switch.checked,
      block_dns_leaks: f.elements.block_dns_leaks.checked, dns: split(v("dns")),
      split: { mode: f.elements.split_mode.value, networks: split(v("split_networks")) }, settings: {}, secrets: {},
    };
    if (kind === "wireguard" && role === "client") {
      if (v("import")) data.import = f.elements.import.value;
      else data.settings = { address: split(v("wg_address")), peer_public_key: v("wg_peer"), endpoint: v("wg_endpoint") };
    } else if (kind === "wireguard") {
      data.settings = { subnet: v("srv_subnet"), listen_port: parseInt(v("srv_port"), 10) || 51820, public_host: v("srv_host"),
        lan_access: f.elements.srv_lan.checked };
    } else if (kind === "openvpn") {
      data.import = f.elements.ovpn.value;
      data.secrets = { username: v("ovpn_user"), password: f.elements.ovpn_pass.value };
    } else if (kind === "ipsec") {
      data.settings = { server: v("ike_server"), auth: f.elements.ike_auth.value, remote_id: v("ike_remote"), local_id: v("ike_local"), username: v("ike_user") };
      data.secrets = { secret: f.elements.ike_secret.value };
    } else if (kind === "tailscale") {
      data.settings = { login_server: v("ts_server"), exit_node: v("ts_exit"), accept_routes: f.elements.ts_routes.checked };
      data.secrets = { auth_key: v("ts_key") };
    } else {
      data.settings = { network_id: v("zt_network") };
    }
    return data;
  }

  VPN.initForm = () => {
    const f = $("vpn-form");
    $("vpn-new").addEventListener("click", () => { f.reset(); showKind(); f.hidden = false; f.scrollIntoView({ behavior: "smooth" }); });
    $("vpn-cancel").addEventListener("click", () => { f.hidden = true; });
    f.elements.kind.addEventListener("change", showKind);
    f.querySelectorAll("[data-file]").forEach((input) => input.addEventListener("change", async () => {
      const file = input.files && input.files[0];
      if (!file) return;
      if (file.size > 200000) { A.toast("File troppo grande", true); return; }
      f.elements[input.dataset.file].value = await file.text();
      if (!f.elements.name.value) f.elements.name.value = file.name.replace(/\.(conf|ovpn)$/i, "").slice(0, 48);
    }));
    f.addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        const r = await A.api("POST", "/api/vpn/profiles", body(f));
        f.hidden = true;
        VPN.render(r);
        const created = r.created || {};
        A.toast(created.public_key && created.role === "client" ? `VPN creata. Chiave pubblica da dare al server: ${created.public_key}` : "VPN creata");
      } catch (err) { A.toast(err.message, true); }
    });
    showKind();
  };
})();
