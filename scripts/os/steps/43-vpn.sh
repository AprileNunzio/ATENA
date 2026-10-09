#!/usr/bin/env bash
. "$(dirname "$0")/../lib.sh"

PACKAGES=(wireguard-tools openvpn strongswan-swanctl charon-systemd)
VPN_DIR=/etc/atena/vpn

wanted() { [ "${ATENA_VPN:-1}" != "0" ]; }

step_check() {
    wanted || return 0
    pkgs_present "${PACKAGES[@]}" || return 1
    [ -d "$VPN_DIR" ] && [ "$(stat -c %a "$VPN_DIR")" = "700" ] || return 1
    systemctl is-enabled --quiet strongswan 2>/dev/null || return 1
}

step_apply() {
    if ! wanted; then
        progress 100 "VPN disattivate"
        return 0
    fi
    progress 20 "WireGuard, OpenVPN e strongSwan"
    apt_install "${PACKAGES[@]}"

    progress 60 "Cartella protetta per le configurazioni"
    install -d -m 0700 -o root -g root "$VPN_DIR"

    progress 80 "Servizio IKEv2"
    systemctl enable --now strongswan >/dev/null 2>&1 || warn "strongSwan non avviato: le VPN IPsec non saranno disponibili"
    command -v tailscale >/dev/null 2>&1 || info "Tailscale non installato: installalo dal sito ufficiale per usarlo con Atena"
    command -v zerotier-cli >/dev/null 2>&1 || info "ZeroTier non installato: installalo dal sito ufficiale per usarlo con Atena"
    progress 100 "VPN pronte"
}

step_main "$@"
