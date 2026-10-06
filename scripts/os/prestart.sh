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
if [ "$(cat "$STAMP" 2>/dev/null)" != "$want" ]; then
    echo "Aggiornamento librerie in background..."
    (
        "$VENV/bin/pip" install -q --upgrade pip
        "$VENV/bin/pip" install -q -r "$REQ"
        echo "$want" > "$STAMP"
    ) &
fi

pkill -f 'backend/wizard_server.py' >/dev/null 2>&1 || true

if [ ! -f /etc/pam.d/atena-admin ]; then
    printf '%s\n' '# Atena OS admin panel' '@include common-auth' '@include common-account' > /etc/pam.d/atena-admin
fi
getent group atena-admin >/dev/null || groupadd --system atena-admin
