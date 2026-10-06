#!/usr/bin/env bash
. "$(dirname "$0")/../lib.sh"

AUTO_UPGRADES=/etc/apt/apt.conf.d/20auto-upgrades
JOURNAL_CONF=/etc/systemd/journald.conf.d/atena.conf
LOGROTATE=/etc/logrotate.d/atena
CTL=/usr/local/bin/atenactl

auto_upgrades() {
    printf '%s\n' \
        '// Gestito da Atena OS: aggiornamenti di sicurezza automatici' \
        'APT::Periodic::Update-Package-Lists "1";' \
        'APT::Periodic::Unattended-Upgrade "1";' \
        'APT::Periodic::AutocleanInterval "7";'
}

journal_conf() {
    printf '%s\n' '# Gestito da Atena OS' '[Journal]' 'SystemMaxUse=500M' 'MaxRetentionSec=1month'
}

logrotate_conf() {
    printf '%s\n' \
        '/var/log/atena/*.log {' \
        '    weekly' \
        '    rotate 8' \
        '    maxsize 50M' \
        '    compress' \
        '    missingok' \
        '    notifempty' \
        '    copytruncate' \
        '}'
}

step_check() {
    auto_upgrades | same_content "$AUTO_UPGRADES" \
        && journal_conf | same_content "$JOURNAL_CONF" \
        && logrotate_conf | same_content "$LOGROTATE" \
        && [ "$(readlink -f "$CTL")" = "$ATENA_DIR/scripts/os/atenactl" ] && [ -x "$CTL" ]
}

step_apply() {
    progress 30 "Aggiornamenti di sicurezza automatici"
    apt_install unattended-upgrades
    auto_upgrades | write_if_changed "$AUTO_UPGRADES" || true
    progress 60 "Limiti del journal di sistema"
    if journal_conf | write_if_changed "$JOURNAL_CONF"; then
        systemctl restart systemd-journald || true
    fi
    progress 85 "Rotazione dei log Atena"
    logrotate_conf | write_if_changed "$LOGROTATE" || true
    chmod +x "$ATENA_DIR/scripts/os/atenactl"
    ln -sfn "$ATENA_DIR/scripts/os/atenactl" "$CTL"
    progress 100 "Manutenzione autonoma attiva (comando atenactl disponibile)"
}

step_main "$@"
