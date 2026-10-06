#!/usr/bin/env bash
set -Eeuo pipefail

REPO_URL="${ATENA_REPO:-https://github.com/AprileNunzio/ATENA.git}"
BRANCH="${ATENA_BRANCH:-main}"
ATENA_DIR=/opt/Atena

C='\033[0;36m'; G='\033[0;32m'; R='\033[0;31m'; N='\033[0m'
say()  { echo -e "${C}[Atena]${N} $*"; }
ok()   { echo -e "${G}[  OK  ]${N} $*"; }
die()  { echo -e "${R}[ERRORE]${N} $*" >&2; exit 1; }
trap 'die "Bootstrap interrotto alla riga $LINENO"' ERR

[ "$EUID" -eq 0 ] || die "Eseguire come root (sudo)."
command -v apt-get >/dev/null 2>&1 || die "Atena OS richiede Debian o Ubuntu."
export DEBIAN_FRONTEND=noninteractive

echo -e "${C}"
echo "   ╔═══════════════════════════════════════════╗"
echo "   ║     A.T.E.N.A.  —  Atena OS Bootstrap     ║"
echo "   ╚═══════════════════════════════════════════╝"
echo -e "${N}"

say "1/5 Riparazione e prerequisiti minimi…"
dpkg --configure -a || true
apt-get update -q
apt-get install -y -q --no-install-recommends git curl ca-certificates python3 python3-venv jq

say "2/5 Download di Atena OS ($BRANCH)…"
git config --global --add safe.directory "$ATENA_DIR" || true
if [ -d "$ATENA_DIR/.git" ]; then
    git -C "$ATENA_DIR" fetch --quiet origin "$BRANCH"
    git -C "$ATENA_DIR" reset --hard --quiet "origin/$BRANCH"
else
    rm -rf "$ATENA_DIR"
    git clone --quiet --branch "$BRANCH" "$REPO_URL" "$ATENA_DIR"
fi
ok "Repository in $ATENA_DIR ($(git -C "$ATENA_DIR" rev-parse --short HEAD))"

say "3/5 Configurazione di base…"
mkdir -p /etc/atena /var/lib/atena /var/log/atena
touch /etc/atena/atena.env
chmod 700 /etc/atena
chmod 600 /etc/atena/atena.env
grep -q '^ATENA_UPDATE_BRANCH=' /etc/atena/atena.env || echo "ATENA_UPDATE_BRANCH=$BRANCH" >> /etc/atena/atena.env
grep -q '^ATENA_AUTO_UPDATE=' /etc/atena/atena.env || echo "ATENA_AUTO_UPDATE=1" >> /etc/atena/atena.env

getent group atena-admin >/dev/null || groupadd --system atena-admin
for candidate in "${SUDO_USER:-}" "$(getent passwd 1000 | cut -d: -f1)"; do
    if [ -n "$candidate" ] && [ "$candidate" != "root" ] && id "$candidate" >/dev/null 2>&1; then
        usermod -aG atena-admin "$candidate"
        ok "Utente '$candidate' abilitato al pannello di amministrazione"
    fi
done

say "4/5 Installazione di Atena Supervisor…"
pkill -f 'backend/wizard_server.py' >/dev/null 2>&1 || true
systemctl disable atena-updater.service >/dev/null 2>&1 || true
rm -f /etc/systemd/system/atena-updater.service
install -m 0644 "$ATENA_DIR/scripts/os/systemd/atena-supervisor.service" /etc/systemd/system/
install -m 0644 "$ATENA_DIR/scripts/os/systemd/atena-rollback.service" /etc/systemd/system/
bash "$ATENA_DIR/scripts/os/prestart.sh"
systemctl daemon-reload
systemctl enable atena-supervisor.service >/dev/null
systemctl restart atena-supervisor.service

for _ in $(seq 1 30); do
    curl -fs -o /dev/null http://127.0.0.1/healthz && break
    sleep 1
done
curl -fs -o /dev/null http://127.0.0.1/healthz || die "Il Supervisor non risponde: journalctl -u atena-supervisor"
ok "Supervisor attivo"

IP=$(hostname -I 2>/dev/null | awk '{print $1}')
say "5/5 Il Supervisor sta completando l'installazione in autonomia."
echo
echo -e "   Monitor installazione / Atena:  ${G}http://${IP:-localhost}/${N}"
echo -e "   Pannello di amministrazione:     ${G}http://${IP:-localhost}:8080/${N}"
echo -e "   Log in tempo reale:              journalctl -fu atena-supervisor"
echo
