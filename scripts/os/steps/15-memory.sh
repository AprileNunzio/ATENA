#!/usr/bin/env bash
. "$(dirname "$0")/../lib.sh"

ZRAM_CONF=/etc/default/zramswap
SYSCTL=/etc/sysctl.d/90-atena-memory.conf

wanted() { [ "${ATENA_ZRAM:-auto}" != "0" ] && [ "$(ram_mb)" -lt 16384 ]; }
percent() { if [ "$(ram_mb)" -lt 7680 ]; then echo 75; else echo 50; fi; }
zram_active() { swapon --show=NAME --noheadings 2>/dev/null | grep -q zram; }
sd_swap_active() { systemctl is-active --quiet dphys-swapfile 2>/dev/null; }

zram_conf() { printf 'ALGO=zstd\nPERCENT=%s\nPRIORITY=100\n' "$(percent)"; }
sysctl_conf() {
    printf '%s\n' "vm.swappiness = 150" "vm.page-cluster = 0" "vm.watermark_boost_factor = 0" "vm.watermark_scale_factor = 125"
}

step_check() {
    wanted || return 0
    zram_active || return 1
    same_content "$SYSCTL" < <(sysctl_conf) || return 1
    [ "$(machine_class)" != pi ] || ! sd_swap_active
}

step_apply() {
    if ! wanted; then
        progress 100 "Memoria sufficiente: nessuna memoria di scorta necessaria"
        return 0
    fi
    if ! zram_active; then
        progress 20 "Installazione della memoria compressa"
        apt_install zram-tools || fail "Pacchetto zram-tools non installato"
        progress 50 "Configurazione: $(percent)% della RAM, compressione zstd"
        write_if_changed "$ZRAM_CONF" < <(zram_conf) || true
        systemctl enable zramswap >/dev/null 2>&1
        systemctl restart zramswap
        wait_for 15 zram_active || fail "La memoria compressa non si è attivata"
    fi
    progress 75 "Regolazione del kernel per la memoria compressa"
    if write_if_changed "$SYSCTL" < <(sysctl_conf); then sysctl -q -p "$SYSCTL" || warn "Parametri del kernel non applicati"; fi
    if [ "$(machine_class)" = pi ] && sd_swap_active; then
        progress 90 "Spegnimento dello swap su scheda SD per non consumarla"
        dphys-swapfile swapoff 2>/dev/null || true
        systemctl disable --now dphys-swapfile >/dev/null 2>&1 || true
    fi
    info "Memoria compressa attiva: $(swapon --show=SIZE --noheadings 2>/dev/null | head -1 | xargs)"
    progress 100 "Memoria compressa attiva"
}

step_main "$@"
