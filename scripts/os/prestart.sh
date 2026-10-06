#!/usr/bin/env bash
set -Eeuo pipefail

ATENA_DIR="${ATENA_DIR:-/opt/Atena}"
WIZ="$ATENA_DIR/installer_wizard"
VENV="$WIZ/venv"
REQ="$WIZ/backend/requirements.txt"
STAMP="$VENV/.requirements.sha1"

mkdir -p /etc/atena /var/lib/atena /var/log/atena
touch /etc/atena/atena.env
chmod 700 /etc/atena
chmod 600 /etc/atena/atena.env

if ! "$VENV/bin/python" -c "import fastapi, uvicorn, httpx, psutil, pam" >/dev/null 2>&1 \
        && [ -f "$STAMP" ]; then
    echo "Ambiente Python corrotto: ricostruzione"
    rm -rf "$VENV"
fi
if [ ! -x "$VENV/bin/pip" ]; then
    rm -rf "$VENV"
    python3 -m venv "$VENV"
fi
want=$(sha1sum "$REQ" | cut -c1-40)
have=$(cat "$STAMP" 2>/dev/null || true)
install_requirements() {
    flock -w 1800 9 || return 1
    [ "$(cat "$STAMP" 2>/dev/null || true)" = "$want" ] && return 0
    "$VENV/bin/pip" install "$@" --disable-pip-version-check --no-input --upgrade pip || return 1
    "$VENV/bin/pip" install "$@" --disable-pip-version-check --no-input -r "$REQ" || return 1
    echo "$want" > "$STAMP.tmp" && mv -f "$STAMP.tmp" "$STAMP"
}
if [ -z "$have" ] || ! "$VENV/bin/python" -c "import fastapi, uvicorn, httpx, psutil, pam" >/dev/null 2>&1; then
    echo "Installazione delle librerie Python di Atena, può richiedere alcuni minuti..."
    install_requirements --progress-bar off 9>"$VENV/.requirements.lock"
elif [ "$have" != "$want" ]; then
    echo "Aggiornamento librerie in background..."
    ( install_requirements -q 9>"$VENV/.requirements.lock" || true ) &
fi

pkill -f 'backend/wizard_server.py' >/dev/null 2>&1 || true

units_changed=0
for unit in atena-supervisor.service atena-rollback.service; do
    src="$ATENA_DIR/scripts/os/systemd/$unit"
    if [ -f "$src" ] && ! cmp -s "$src" "/etc/systemd/system/$unit"; then
        install -m 0644 "$src" /etc/systemd/system/
        units_changed=1
    fi
done
if [ "$units_changed" = 1 ]; then systemctl daemon-reload >/dev/null 2>&1 || true; fi

if [ ! -f /etc/pam.d/atena-admin ]; then
    printf '%s\n' '# Atena OS admin panel' '@include common-auth' '@include common-account' > /etc/pam.d/atena-admin
fi
getent group atena-admin >/dev/null || groupadd --system atena-admin
