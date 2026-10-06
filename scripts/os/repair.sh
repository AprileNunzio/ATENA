#!/usr/bin/env bash
set -uo pipefail
export DEBIAN_FRONTEND=noninteractive

ATENA_DIR="${ATENA_DIR:-/opt/Atena}"
WIZ="$ATENA_DIR/installer_wizard"
VENV="$WIZ/venv"
REQ="$WIZ/backend/requirements.txt"
STAMP="$VENV/.requirements.sha1"
STATE=/var/lib/atena
STATUS="$STATE/repair.json"
LOG_DIR=/var/log/atena
LOG="$LOG_DIR/repair.log"
UNIT=atena-supervisor.service
CORE_IMPORTS="import fastapi, uvicorn, httpx, psutil, pam"
RESTART=1
QUIET=0
ORIGIN=manual

for arg in "$@"; do
    case "$arg" in
        --no-restart) RESTART=0 ;;
        --quiet) QUIET=1 ;;
        --origin=*) ORIGIN=${arg#--origin=} ;;
    esac
done

[ "$EUID" -eq 0 ] || { echo "sudo atenactl ripara" >&2; exit 2; }
mkdir -p "$STATE" "$LOG_DIR"
chmod 750 "$LOG_DIR"

ui_lang=""
if [ -r /etc/atena/atena.env ]; then ui_lang=$(sed -n 's/^ATENA_UI_LANG=//p' /etc/atena/atena.env | tail -n 1); fi
case "${ui_lang:-${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}}" in
    it*) UI_LANG=it ;;
    *) UI_LANG=en ;;
esac

declare -A L
if [ "$UI_LANG" = it ]; then
    L=(
        [title]="Riparazione di Atena" [busy]="Un'altra riparazione è già in corso"
        [disk]="Spazio su disco" [apt]="Gestore dei pacchetti" [network]="Connessione a internet"
        [code]="File di Atena" [python]="Librerie Python" [system]="File di sistema" [ports]="Porte di rete"
        [service]="Avvio di Atena"
        [disk_ok]="liberi" [disk_cleaned]="liberati con la pulizia" [disk_full]="spazio insufficiente: libera almeno 2 GB e riprova"
        [apt_wait]="attendo che finisca un'altra installazione" [apt_fixed]="installazione interrotta completata" [apt_failed]="il gestore dei pacchetti non risponde"
        [net_fixed]="ripristinata riavviando la risoluzione dei nomi" [net_offline]="assente: controlla cavo o Wi-Fi"
        [code_fixed]="file danneggiati ripristinati" [code_fetched]="riscaricati da GitHub" [code_failed]="non è stato possibile ripristinarli"
        [py_fixed]="reinstallate" [py_rebuilt]="ambiente ricostruito da zero" [py_failed]="installazione non riuscita" [py_wait]="in attesa di un'altra installazione"
        [sys_fixed]="ripristinati"
        [port_busy]="la porta %s è occupata da %s: chiudi quel programma"
        [svc_ok]="attiva" [svc_safe]="partita in modalità sicura" [svc_failed]="non risponde"
        [ok]="ok" [done]="Riparazione completata: Atena funziona" [partial]="Riparazione terminata con problemi da risolvere a mano"
        [log]="Log completo"
    )
else
    L=(
        [title]="Atena repair" [busy]="Another repair is already running"
        [disk]="Disk space" [apt]="Package manager" [network]="Internet connection"
        [code]="Atena files" [python]="Python libraries" [system]="System files" [ports]="Network ports"
        [service]="Starting Atena"
        [disk_ok]="free" [disk_cleaned]="freed by cleanup" [disk_full]="not enough space: free at least 2 GB and try again"
        [apt_wait]="waiting for another installation to finish" [apt_fixed]="interrupted installation completed" [apt_failed]="the package manager is not responding"
        [net_fixed]="restored by restarting name resolution" [net_offline]="offline: check the cable or Wi-Fi"
        [code_fixed]="damaged files restored" [code_fetched]="downloaded again from GitHub" [code_failed]="could not be restored"
        [py_fixed]="reinstalled" [py_rebuilt]="environment rebuilt from scratch" [py_failed]="installation failed" [py_wait]="waiting for another installation"
        [sys_fixed]="restored"
        [port_busy]="port %s is used by %s: close that program"
        [svc_ok]="running" [svc_safe]="started in safe mode" [svc_failed]="not responding"
        [ok]="ok" [done]="Repair complete: Atena is working" [partial]="Repair finished with problems to fix by hand"
        [log]="Full log"
    )
fi

if [ -t 1 ] && [ "$QUIET" = 0 ]; then
    C_OK=$'\033[32m' C_WARN=$'\033[33m' C_BAD=$'\033[31m' C_DIM=$'\033[2m' C_CYAN=$'\033[36m' C_OFF=$'\033[0m'
else
    C_OK="" C_WARN="" C_BAD="" C_DIM="" C_CYAN="" C_OFF=""
fi

exec 8>/run/atena-repair.lock
if ! flock -n 8; then
    [ "$QUIET" = 1 ] || echo "${L[busy]}"
    exit 0
fi

KEYS=(disk apt network code python system ports service)
declare -A ST DT
for k in "${KEYS[@]}"; do ST[$k]=pending DT[$k]=""; done
STARTED=$EPOCHSECONDS
OVERALL=running
FAILED=0

write_status() {
    local steps=() k tmp
    for k in "${KEYS[@]}"; do
        steps+=("$(jq -cn --arg k "$k" --arg s "${ST[$k]}" --arg d "${DT[$k]}" '{key:$k,status:$s,detail:$d}')")
    done
    tmp=$(mktemp "$STATE/.repair.XXXXXX") || return 0
    printf '[%s]' "$(IFS=,; echo "${steps[*]}")" \
        | jq -c --arg st "$OVERALL" --arg o "$ORIGIN" --argjson t0 "$STARTED" --argjson t1 "$EPOCHSECONDS" --arg lang "$UI_LANG" \
            '{state:$st,origin:$o,started:$t0,updated:$t1,lang:$lang,steps:.}' > "$tmp" 2>/dev/null \
        && chmod 644 "$tmp" && mv -f "$tmp" "$STATUS"
    rm -f "$tmp"
}

mark() {
    local key=$1 status=$2 detail=${3:-} icon color
    ST[$key]=$status DT[$key]=$detail
    write_status
    printf '[%s] %s %s %s\n' "$(date -Is)" "$key" "$status" "$detail" >> "$LOG"
    [ "$QUIET" = 1 ] && return 0
    case "$status" in
        running) return 0 ;;
        ok) icon="✓" color=$C_OK ;;
        fixed) icon="✓" color=$C_WARN ;;
        *) icon="✗" color=$C_BAD ;;
    esac
    printf '   %s%s%s %-24s %s%s%s\n' "$color" "$icon" "$C_OFF" "${L[$key]}" "$C_DIM" "${detail:-${L[ok]}}" "$C_OFF"
}

fail_step() { FAILED=1; mark "$1" failed "$2"; }

human_mb() {
    local mb=$1 dec=","
    [ "$UI_LANG" = it ] || dec="."
    if (( mb >= 1024 )); then printf '%d%s%d GB' $(( mb / 1024 )) "$dec" $(( mb % 1024 * 10 / 1024 )); else printf '%d MB' "$mb"; fi
}

free_mb() { df -Pm / | awk 'NR==2 {print $4+0}'; }

check_disk() {
    mark disk running
    local before after
    before=$(free_mb)
    if (( before >= 3072 )); then mark disk ok "$(human_mb "$before") ${L[disk_ok]}"; return 0; fi
    apt-get clean >>"$LOG" 2>&1
    journalctl --vacuum-size=200M >>"$LOG" 2>&1
    [ -x "$VENV/bin/pip" ] && "$VENV/bin/pip" cache purge >>"$LOG" 2>&1
    rm -rf /root/.cache/pip
    find /tmp -xdev -type f -atime +2 -delete 2>/dev/null
    command -v docker >/dev/null 2>&1 && docker image prune -f >>"$LOG" 2>&1
    after=$(free_mb)
    if (( after < 2048 )); then fail_step disk "$(human_mb "$after") ${L[disk_ok]}: ${L[disk_full]}"; return 1; fi
    mark disk fixed "$(human_mb $(( after - before ))) ${L[disk_cleaned]}"
}

apt_busy() { pgrep -x apt-get >/dev/null || pgrep -x apt >/dev/null || pgrep -x dpkg >/dev/null || pgrep -x unattended-upgr >/dev/null; }

check_apt() {
    mark apt running
    local waited=0 fixed=0
    while apt_busy && (( waited < 900 )); do
        (( waited == 0 )) && mark apt running "${L[apt_wait]}"
        sleep 5
        waited=$(( waited + 5 ))
    done
    if apt_busy; then fail_step apt "${L[apt_failed]}"; return 1; fi
    if [ -n "$(dpkg --audit 2>/dev/null)" ]; then
        dpkg --configure -a >>"$LOG" 2>&1
        apt-get -f install -y -q >>"$LOG" 2>&1
        fixed=1
    fi
    if [ -n "$(dpkg --audit 2>/dev/null)" ]; then fail_step apt "${L[apt_failed]}"; return 1; fi
    if (( fixed )); then mark apt fixed "${L[apt_fixed]}"; else mark apt ok; fi
}

online() {
    curl -fsS --proto '=https' --max-time 8 -o /dev/null "https://github.com/AprileNunzio/ATENA.git/info/refs?service=git-upload-pack" \
        && curl -fsS --proto '=https' --max-time 8 -o /dev/null https://pypi.org/simple/pip/
}

NET=1
check_network() {
    mark network running
    if online; then mark network ok; return 0; fi
    systemctl restart systemd-resolved >>"$LOG" 2>&1
    systemctl restart NetworkManager >>"$LOG" 2>&1
    local i
    for i in 1 2 3 4 5 6; do
        sleep 5
        if online; then mark network fixed "${L[net_fixed]}"; return 0; fi
    done
    NET=0
    fail_step network "${L[net_offline]}"
    return 1
}

git_a() { git -c safe.directory='*' -C "$ATENA_DIR" "$@"; }

check_code() {
    mark code running
    local head branch remote tmp
    branch=$(sed -n 's/^ATENA_UPDATE_BRANCH=//p' /etc/atena/atena.env 2>/dev/null | tail -n 1)
    branch=${branch:-main}
    if head=$(git_a rev-parse --verify -q HEAD 2>>"$LOG") && git_a fsck --connectivity-only --no-dangling >>"$LOG" 2>&1; then
        if git_a diff --quiet HEAD -- 2>>"$LOG"; then mark code ok "${head:0:7}"; return 0; fi
        if git_a reset --hard -q HEAD >>"$LOG" 2>&1; then mark code fixed "${L[code_fixed]}"; return 0; fi
    fi
    if (( NET == 0 )); then fail_step code "${L[code_failed]}"; return 1; fi
    remote=$(git_a remote get-url origin 2>/dev/null || echo "https://github.com/AprileNunzio/ATENA.git")
    case "$remote" in https://*) ;; *) remote="https://github.com/AprileNunzio/ATENA.git" ;; esac
    tmp="$ATENA_DIR.repair.$$"
    rm -rf "$tmp"
    if ! git clone -q --branch "$branch" "$remote" "$tmp" >>"$LOG" 2>&1; then rm -rf "$tmp"; fail_step code "${L[code_failed]}"; return 1; fi
    if [ -n "${head:-}" ] && git -C "$tmp" cat-file -e "$head^{commit}" 2>/dev/null; then git -C "$tmp" reset -q --hard "$head" >>"$LOG" 2>&1; fi
    rm -rf "$ATENA_DIR.broken"
    mv "$ATENA_DIR" "$ATENA_DIR.broken" && mv "$tmp" "$ATENA_DIR" && rm -rf "$ATENA_DIR.broken"
    mark code fixed "${L[code_fetched]}"
}

pip_install() {
    "$VENV/bin/pip" install -q --disable-pip-version-check --no-input --upgrade pip >>"$LOG" 2>&1 \
        && "$VENV/bin/pip" install -q --disable-pip-version-check --no-input -r "$REQ" >>"$LOG" 2>&1 \
        && "$VENV/bin/python" -c "$CORE_IMPORTS" >>"$LOG" 2>&1 \
        && echo "$want" > "$STAMP.tmp" && mv -f "$STAMP.tmp" "$STAMP"
}

safe_reason() { jq -r '.reason // ""' "$STATE/safe_mode.json" 2>/dev/null; }

check_python() {
    mark python running
    want=$(sha1sum "$REQ" 2>/dev/null | cut -c1-40)
    local healthy=1
    [ -x "$VENV/bin/python" ] || healthy=0
    (( healthy )) && { "$VENV/bin/python" -c "$CORE_IMPORTS" >/dev/null 2>&1 || healthy=0; }
    (( healthy )) && { [ "$(cat "$STAMP" 2>/dev/null)" = "$want" ] || healthy=0; }
    (( healthy )) && { "$VENV/bin/pip" check >>"$LOG" 2>&1 || healthy=0; }
    [ "$(safe_reason)" = missing_library ] && healthy=0
    if (( healthy )); then mark python ok; return 0; fi
    if (( NET == 0 )); then fail_step python "${L[py_failed]}"; return 1; fi
    exec 9>>"$VENV/.requirements.lock" 2>/dev/null || exec 9>/run/atena-requirements.lock
    if ! flock -n 9; then
        mark python running "${L[py_wait]}"
        flock -w 1800 9 || { fail_step python "${L[py_failed]}"; return 1; }
    fi
    if [ -x "$VENV/bin/pip" ] && pip_install; then exec 9>&-; mark python fixed "${L[py_fixed]}"; return 0; fi
    rm -rf /root/.cache/pip "$VENV"
    python3 -m venv "$VENV" >>"$LOG" 2>&1 || { exec 9>&-; fail_step python "${L[py_failed]}"; return 1; }
    exec 9>>"$VENV/.requirements.lock"
    if "$VENV/bin/pip" install -q --no-cache-dir --disable-pip-version-check --no-input --upgrade pip >>"$LOG" 2>&1 \
        && "$VENV/bin/pip" install -q --no-cache-dir --disable-pip-version-check --no-input -r "$REQ" >>"$LOG" 2>&1 \
        && "$VENV/bin/python" -c "$CORE_IMPORTS" >>"$LOG" 2>&1; then
        echo "$want" > "$STAMP"
        exec 9>&-
        mark python fixed "${L[py_rebuilt]}"
        return 0
    fi
    exec 9>&-
    fail_step python "${L[py_failed]}"
    return 1
}

check_system() {
    mark system running
    local changed=0 unit
    for unit in atena-supervisor.service atena-rollback.service; do
        if [ -f "$ATENA_DIR/scripts/os/systemd/$unit" ] && ! cmp -s "$ATENA_DIR/scripts/os/systemd/$unit" "/etc/systemd/system/$unit"; then
            install -m 0644 "$ATENA_DIR/scripts/os/systemd/$unit" /etc/systemd/system/
            changed=1
        fi
    done
    (( changed )) && systemctl daemon-reload >>"$LOG" 2>&1
    if [ ! -f /etc/pam.d/atena-admin ]; then
        printf '%s\n' '# Atena OS admin panel' '@include common-auth' '@include common-account' > /etc/pam.d/atena-admin
        changed=1
    fi
    getent group atena-admin >/dev/null || { groupadd --system atena-admin; changed=1; }
    mkdir -p /etc/atena /var/lib/atena /var/log/atena
    touch /etc/atena/atena.env
    [ "$(stat -c %a /etc/atena)" = 700 ] || { chmod 700 /etc/atena; changed=1; }
    [ "$(stat -c %a /etc/atena/atena.env)" = 600 ] || { chmod 600 /etc/atena/atena.env; changed=1; }
    systemctl is-enabled -q "$UNIT" 2>/dev/null || { systemctl enable -q "$UNIT" >>"$LOG" 2>&1; changed=1; }
    if (( changed )); then mark system fixed "${L[sys_fixed]}"; else mark system ok; fi
}

port_owner() {
    ss -Hltnp "sport = :$1" 2>/dev/null | grep -o 'users:(("[^"]*",pid=[0-9]*' | head -n 1 | sed 's/users:(("\([^"]*\)",pid=\([0-9]*\)/\1 \2/'
}

check_ports() {
    mark ports running
    local port owner name pid msg
    if systemctl is-active -q "$UNIT"; then mark ports ok; return 0; fi
    for port in 80 8080; do
        owner=$(port_owner "$port")
        [ -n "$owner" ] || continue
        read -r name pid <<< "$owner"
        if [ -n "$pid" ] && tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null | grep -q "$WIZ/"; then
            kill "$pid" 2>/dev/null
            continue
        fi
        printf -v msg "${L[port_busy]}" "$port" "$name"
        fail_step ports "$msg"
        return 1
    done
    mark ports ok
}

healthz() { curl -fsS --max-time 3 http://127.0.0.1/healthz 2>/dev/null; }

check_service() {
    mark service running
    if (( RESTART == 0 )); then mark service ok; return 0; fi
    systemctl reset-failed "$UNIT" >>"$LOG" 2>&1
    systemctl restart --no-block "$UNIT" >>"$LOG" 2>&1
    local i body=""
    sleep 3
    for (( i = 0; i < 90; i++ )); do
        body=$(healthz) && break
        sleep 2
    done
    if [ -z "$body" ]; then
        journalctl -u "$UNIT" -n 60 --no-pager >>"$LOG" 2>&1
        fail_step service "${L[svc_failed]}"
        return 1
    fi
    if jq -e '.safe_mode == true' >/dev/null 2>&1 <<< "$body"; then fail_step service "${L[svc_safe]}"; return 1; fi
    curl -fsS --max-time 10 -X POST -H "X-Atena-Request: 1" http://127.0.0.1:8080/api/internal/repair >>"$LOG" 2>&1
    mark service ok "${L[svc_ok]}"
}

[ "$QUIET" = 1 ] || printf '\n   %s%s%s\n\n' "$C_CYAN" "${L[title]}" "$C_OFF"
printf '\n=== %s repair (%s) ===\n' "$(date -Is)" "$ORIGIN" >> "$LOG"
write_status

if check_disk; then
    check_apt
    check_network
    check_code
    check_python
    check_system
    if check_ports; then check_service; else ST[service]=skipped; fi
fi
for k in "${KEYS[@]}"; do [ "${ST[$k]}" = pending ] && ST[$k]=skipped; done

if (( FAILED )); then OVERALL=failed; else OVERALL=done; fi
write_status
if [ "$QUIET" = 0 ]; then
    if (( FAILED )); then printf '\n   %s%s%s\n' "$C_BAD" "${L[partial]}" "$C_OFF"; else printf '\n   %s%s%s\n' "$C_OK" "${L[done]}" "$C_OFF"; fi
    printf '   %s%s: %s%s\n\n' "$C_DIM" "${L[log]}" "$LOG" "$C_OFF"
fi
exit "$FAILED"
