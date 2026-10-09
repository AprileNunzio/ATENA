#!/usr/bin/env bash
. "$(dirname "$0")/../lib.sh"

UNIT_SRC="$ATENA_DIR/scripts/os/systemd/atena-netguard.service"
UNIT_DST=/etc/systemd/system/atena-netguard.service
BIN="${ATENA_NATIVE_HOME:-/opt/atena-native}/bin/atena-netguard"
ENV_FILE=/etc/atena/netguard.env
CONFIG=/etc/atena/netguard.json
SOCKET=/run/atena/netguard/netguard.sock

wanted() { [ "${ATENA_NETGUARD:-1}" != "0" ] && [ "${ATENA_NATIVE:-auto}" != "0" ]; }

interfaces() {
    if [ -n "${ATENA_NETGUARD_INTERFACES:-}" ]; then
        tr ', ' '\n\n' <<< "$ATENA_NETGUARD_INTERFACES" | grep -E '^[A-Za-z0-9_.:-]{1,15}$'
        return
    fi
    local dev name
    for dev in /sys/class/net/*; do
        name=$(basename "$dev")
        [ "$name" = lo ] && continue
        [ -e "$dev/device" ] || [ -d "$dev/wireless" ] || continue
        echo "$name"
    done
}

env_conf() {
    local args="" name
    for name in $(interfaces); do args="$args --interface $name"; done
    [ -f "$CONFIG" ] && args="$args --config $CONFIG"
    printf '%s\n' '# Gestito da Atena OS — interfacce analizzate dal firewall' "NETGUARD_ARGS=\"${args# }\""
}

step_check() {
    if ! wanted; then
        ! systemctl is-enabled --quiet atena-netguard 2>/dev/null
        return
    fi
    [ -x "$BIN" ] || return 0
    command -v nft >/dev/null 2>&1 || return 1
    env_conf | same_content "$ENV_FILE" || return 1
    code_current netguard "$UNIT_SRC" "$BIN" || return 1
    systemctl is-active --quiet atena-netguard && [ -S "$SOCKET" ]
}

step_apply() {
    if ! wanted; then
        progress 50 "Analisi del traffico disattivata"
        systemctl disable --now atena-netguard >/dev/null 2>&1 || true
        rm -f "$UNIT_DST"
        systemctl daemon-reload
        progress 100 "Analisi del traffico disattivata"
        return 0
    fi
    progress 10 "Strumenti nftables"
    apt_install nftables
    if [ ! -x "$BIN" ]; then
        progress 100 "Motore nativo non ancora compilato: l'analisi del traffico partirà al prossimo controllo"
        return 0
    fi
    [ -n "$(interfaces)" ] || { warn "Nessuna interfaccia ethernet o wifi trovata"; progress 100 "Nessuna interfaccia da analizzare"; return 0; }

    progress 40 "Interfacce da analizzare: $(interfaces | tr '\n' ' ')"
    install -d -m 0755 /etc/atena
    env_conf | write_if_changed "$ENV_FILE" || true
    chmod 0644 "$ENV_FILE"

    progress 70 "Servizio di analisi del traffico"
    install -m 0644 "$UNIT_SRC" "$UNIT_DST"
    systemctl daemon-reload
    systemctl enable atena-netguard >/dev/null 2>&1
    systemctl restart atena-netguard
    wait_for 30 test -S "$SOCKET" || fail "Il motore di analisi del traffico non si è avviato: journalctl -u atena-netguard"
    code_mark netguard "$UNIT_SRC" "$BIN"
    progress 100 "Firewall: analisi di ethernet e wifi attiva"
}

step_main "$@"
