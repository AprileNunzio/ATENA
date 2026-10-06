#!/usr/bin/env bash
set -Eeuo pipefail

REPO_URL="${ATENA_REPO:-https://github.com/AprileNunzio/ATENA.git}"
BRANCH="${ATENA_BRANCH:-main}"
ATENA_DIR=/opt/Atena
WIZ="$ATENA_DIR/installer_wizard"
VENV="$WIZ/venv"
REQ="$WIZ/backend/requirements.txt"
STAMP="$VENV/.requirements.sha1"
LOG_DIR=/var/log/atena
LOG="$LOG_DIR/bootstrap.log"
PREREQS=(git curl ca-certificates python3 python3-venv jq)
WEIGHT=(0 12 16 62 3 7)

case "${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}" in
    it*) UI_LANG=it ;;
    *) UI_LANG=en ;;
esac

declare -A T
if [ "$UI_LANG" = it ]; then
    DEC=","
    T=(
        [title]="Installazione di base" [elapsed]="trascorsi" [total]="Totale" [eta]="fine prevista"
        [s1]="Prerequisiti di sistema" [s2]="Download di Atena" [s3]="Librerie Python"
        [s4]="Configurazione di base" [s5]="Avvio del Supervisor"
        [repair]="Riparazione dei pacchetti interrotti" [index]="Aggiornamento dell'indice dei pacchetti"
        [present]="già presenti" [package]="pacchetto" [packages]="pacchetti" [of]="di" [left]="mancano" [remaining]="restanti"
        [download]="Scaricamento" [unpack]="Installazione" [objects]="oggetti" [deltas]="Elaborazione delle modifiche"
        [prepare]="Preparazione del download" [checkout]="Estrazione dei file" [venv]="Creazione dell'ambiente Python"
        [pip]="Aggiornamento di pip" [resolve]="Calcolo delle librerie necessarie" [sizes]="Calcolo delle dimensioni"
        [installpy]="Installazione delle librerie" [build]="Compilazione" [lock]="In attesa di un'altra installazione"
        [config]="Configurazione dei servizi" [admin_user]="pannello abilitato per" [start]="Avvio del servizio"
        [waiting]="In attesa della risposta" [ready]="attivo"
        [error]="ERRORE" [root]="Eseguire come root (sudo)." [debian]="Atena OS richiede Debian o Ubuntu."
        [stopped]="Installazione interrotta al passo" [line]="riga" [lastlog]="Ultime righe del log" [fulllog]="Log completo"
        [noresp]="Il Supervisor non risponde" [done]="Installazione di base completata"
        [autonomy]="Il Supervisor completa l'installazione in autonomia."
        [monitor]="Monitor installazione / Atena" [admin]="Pannello di amministrazione" [live]="Log in tempo reale"
    )
else
    DEC="."
    T=(
        [title]="Base installation" [elapsed]="elapsed" [total]="Total" [eta]="expected finish"
        [s1]="System prerequisites" [s2]="Downloading Atena" [s3]="Python libraries"
        [s4]="Base configuration" [s5]="Starting the Supervisor"
        [repair]="Repairing interrupted packages" [index]="Updating the package index"
        [present]="already present" [package]="package" [packages]="packages" [of]="of" [left]="left" [remaining]="remaining"
        [download]="Downloading" [unpack]="Installing" [objects]="objects" [deltas]="Resolving changes"
        [prepare]="Preparing the download" [checkout]="Checking out files" [venv]="Creating the Python environment"
        [pip]="Updating pip" [resolve]="Resolving the required libraries" [sizes]="Measuring download size"
        [installpy]="Installing libraries" [build]="Building" [lock]="Waiting for another installation"
        [config]="Configuring services" [admin_user]="panel enabled for" [start]="Starting the service"
        [waiting]="Waiting for a response" [ready]="running"
        [error]="ERROR" [root]="Run as root (sudo)." [debian]="Atena OS requires Debian or Ubuntu."
        [stopped]="Installation stopped at step" [line]="line" [lastlog]="Last log lines" [fulllog]="Full log"
        [noresp]="The Supervisor is not responding" [done]="Base installation complete"
        [autonomy]="The Supervisor finishes the installation on its own."
        [monitor]="Installation monitor / Atena" [admin]="Admin panel" [live]="Live log"
    )
fi

TTY=0
if [ -t 1 ] && [ "${TERM:-dumb}" != dumb ]; then TTY=1; fi
if [ "$(locale charmap 2>/dev/null || true)" = UTF-8 ]; then
    G_FULL="█" G_EMPTY="░" G_OK="✓" G_RUN="▶" G_WAIT="○" G_BAD="✗" G_DOT="·" G_SPIN=(⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧ ⠇ ⠏) G_PIPE="│"
else
    G_FULL="#" G_EMPTY="-" G_OK="+" G_RUN=">" G_WAIT="o" G_BAD="x" G_DOT="-" G_SPIN=("|" "/" "-" "\\") G_PIPE="|"
fi
if [ "$TTY" = 1 ]; then
    C_CYAN=$'\033[36m' C_GREEN=$'\033[32m' C_RED=$'\033[31m' C_DIM=$'\033[2m' C_BOLD=$'\033[1m' C_OFF=$'\033[0m'
else
    C_CYAN="" C_GREEN="" C_RED="" C_DIM="" C_BOLD="" C_OFF=""
fi
COLS=$(tput cols 2>/dev/null || echo 80)
[[ "$COLS" =~ ^[0-9]+$ ]] || COLS=80
BAR_W=18 TOTAL_W=28
if [ "$COLS" -lt 78 ]; then BAR_W=10 TOTAL_W=16; fi

STEP_STATE=(x wait wait wait wait wait)
STEP_NOTE=("" "" "" "" "" "")
STEP_T0=(0 0 0 0 0 0)
STEP_DUR=(0 0 0 0 0 0)
CUR=0 PCT=0 DETAIL1="" DETAIL2="" DRAWN=0 LAST_DRAW=0 SPIN_I=0 PLAIN_MARK=-1
START=$EPOCHSECONDS
SP_LAST_T=0 SP_LAST_B=0 SPEED=0

fmt_bytes() {
    local _b=$2 _d=1 _u=B _t
    if (( _b >= 1000000000 )); then _d=1000000000 _u=GB
    elif (( _b >= 1000000 )); then _d=1000000 _u=MB
    elif (( _b >= 1000 )); then _d=1000 _u=kB
    fi
    if (( _d == 1 )); then printf -v "$1" '%d B' "$_b"; return 0; fi
    _t=$(( _b * 10 / _d ))
    printf -v "$1" '%d%s%d %s' $(( _t / 10 )) "$DEC" $(( _t % 10 )) "$_u"
}

fmt_dur() {
    local _s=$2
    if (( _s >= 3600 )); then printf -v "$1" '%d:%02d:%02d' $(( _s / 3600 )) $(( _s % 3600 / 60 )) $(( _s % 60 ))
    else printf -v "$1" '%d:%02d' $(( _s / 60 )) $(( _s % 60 ))
    fi
}

fmt_left() {
    local _s=$2
    if (( _s >= 90 )); then printf -v "$1" '~%d min' $(( (_s + 30) / 60 ))
    else printf -v "$1" '~%d s' "$_s"
    fi
}

mkbar() {
    local _p=$2 _w=$3 _f _i _out=""
    (( _p < 0 )) && _p=0
    (( _p > 100 )) && _p=100
    _f=$(( _p * _w / 100 ))
    for (( _i = 0; _i < _w; _i++ )); do
        if (( _i < _f )); then _out+="$G_FULL"; else _out+="$G_EMPTY"; fi
    done
    printf -v "$1" '%s' "$_out"
}

clip() {
    local _s=$2 _max=$(( COLS - ${3:-12} ))
    (( _max < 20 )) && _max=20
    if (( ${#_s} > _max )); then _s="${_s:0:_max-1}…"; fi
    printf -v "$1" '%s' "$_s"
}

overall() {
    local _i _p=0
    for (( _i = 1; _i <= 5; _i++ )); do
        if [ "${STEP_STATE[_i]}" = ok ]; then _p=$(( _p + WEIGHT[_i] * 100 ))
        elif (( _i == CUR )); then _p=$(( _p + WEIGHT[_i] * PCT ))
        fi
    done
    printf -v "$1" '%d' $(( _p / 100 ))
}

speed_update() {
    local now=${EPOCHREALTIME/[.,]/} b=$1 dt inst
    if (( SP_LAST_T == 0 || b < SP_LAST_B )); then SP_LAST_T=$now SP_LAST_B=$b; return 0; fi
    dt=$(( now - SP_LAST_T ))
    (( dt < 1000000 )) && return 0
    inst=$(( (b - SP_LAST_B) * 1000000 / dt ))
    if (( SPEED == 0 )); then SPEED=$inst; else SPEED=$(( (SPEED * 7 + inst * 3) / 10 )); fi
    SP_LAST_T=$now SP_LAST_B=$b
}

speed_reset() { SP_LAST_T=0 SP_LAST_B=0 SPEED=0; }

transfer_lines() {
    local done=$1 total=$2 pct=$3 extra=${4:-} bar d t s left=""
    mkbar bar "$pct" "$BAR_W"
    fmt_bytes d "$done"
    if (( total > 0 )); then fmt_bytes t "$total"; t="$d / $t"; else t="$d"; fi
    DETAIL1="${C_CYAN}${bar}${C_OFF}  $(printf '%3d' "$pct")%  ${t}"
    if (( SPEED > 0 )); then
        fmt_bytes s "$SPEED"
        if (( total > done )); then fmt_left left $(( (total - done) / SPEED + 1 )); left=" $G_DOT ${T[left]} $left"; fi
        DETAIL2="${C_DIM}${s}/s${left}${extra:+ $G_DOT $extra}${C_OFF}"
    else
        DETAIL2="${C_DIM}${extra}${C_OFF}"
    fi
}

render_plain() {
    local p mark
    overall p
    mark=$(( CUR * 1000 + PCT / 10 * 10 ))
    (( mark == PLAIN_MARK )) && return 0
    PLAIN_MARK=$mark
    printf '[Atena] %d/5 %s %3d%%  (%s %d%%)\n' "$CUR" "${T[s$CUR]}" "$PCT" "${T[total]}" "$p"
}

draw() {
    local force=${1:-0} now lines=() i icon name note dur p bar eta line spin
    if [ "$TTY" != 1 ]; then
        (( CUR > 0 )) && [ "${STEP_STATE[CUR]}" = run ] && render_plain
        return 0
    fi
    now=${EPOCHREALTIME/[.,]/}
    if [ "$force" != 1 ] && (( now - LAST_DRAW < 200000 )); then return 0; fi
    LAST_DRAW=$now
    SPIN_I=$(( (SPIN_I + 1) % ${#G_SPIN[@]} ))
    spin=${G_SPIN[SPIN_I]}
    fmt_dur dur $(( EPOCHSECONDS - START ))
    lines+=("   ${C_BOLD}${C_CYAN}A.T.E.N.A.${C_OFF}  ${G_DOT}  ${T[title]}   ${C_DIM}${dur} ${T[elapsed]}${C_OFF}")
    lines+=("")
    for (( i = 1; i <= 5; i++ )); do
        case "${STEP_STATE[i]}" in
            ok) icon="${C_GREEN}${G_OK}${C_OFF}" ;;
            run) icon="${C_CYAN}${G_RUN}${C_OFF}" ;;
            fail) icon="${C_RED}${G_BAD}${C_OFF}" ;;
            *) icon="${C_DIM}${G_WAIT}${C_OFF}" ;;
        esac
        printf -v name '%-26s' "${T[s$i]}"
        note=${STEP_NOTE[i]}
        dur=""
        if [ "${STEP_STATE[i]}" = ok ] || [ "${STEP_STATE[i]}" = fail ]; then fmt_dur dur "${STEP_DUR[i]}"; fi
        if [ "${STEP_STATE[i]}" = wait ]; then
            lines+=("   $icon $i  ${C_DIM}${name}${C_OFF}")
        else
            clip note "$note" 48
            lines+=("   $icon $i  ${name} ${C_DIM}${note}${C_OFF}${dur:+  ${C_DIM}${dur}${C_OFF}}")
        fi
        if (( i == CUR )) && [ "${STEP_STATE[i]}" = run ]; then
            if [ -n "$DETAIL1" ]; then lines+=("        $DETAIL1"); else lines+=(""); fi
            if [ -n "$DETAIL2" ]; then lines+=("        $DETAIL2"); else lines+=("        ${C_DIM}${spin}${C_OFF}"); fi
        fi
    done
    if (( CUR == 0 )) || [ "${STEP_STATE[CUR]}" != run ]; then lines+=("" ""); fi
    lines+=("")
    overall p
    mkbar bar "$p" "$TOTAL_W"
    eta=""
    if (( p >= 4 && p < 100 )) && [ "${STEP_STATE[CUR]}" != fail ]; then
        local el=$(( EPOCHSECONDS - START )) rem clock
        rem=$(( el * (100 - p) / p ))
        printf -v clock '%(%H:%M)T' $(( EPOCHSECONDS + rem ))
        eta="   ${C_DIM}${T[eta]} ~${clock}${C_OFF}"
    fi
    lines+=("   ${C_BOLD}${T[total]}${C_OFF}  ${C_CYAN}${bar}${C_OFF}  $(printf '%3d' "$p")%${eta}")
    if (( DRAWN > 0 )); then printf '\033[%dA' "$DRAWN"; fi
    for line in "${lines[@]}"; do printf '\r\033[K%s\n' "$line"; done
    printf '\033[J'
    DRAWN=${#lines[@]}
}

step_begin() {
    CUR=$1 PCT=0 DETAIL1="" DETAIL2=""
    STEP_STATE[CUR]=run
    STEP_T0[CUR]=$EPOCHSECONDS
    speed_reset
    printf '\n=== %s %d/5 %s ===\n' "$(date -Is)" "$CUR" "${T[s$CUR]}" >> "$LOG"
    draw 1
}

step_end() {
    STEP_STATE[CUR]=ok
    STEP_NOTE[CUR]=$1
    STEP_DUR[CUR]=$(( EPOCHSECONDS - STEP_T0[CUR] ))
    PCT=100 DETAIL1="" DETAIL2=""
    if [ "$TTY" != 1 ]; then printf '[Atena] %d/5 %s %s %s\n' "$CUR" "${T[s$CUR]}" "$G_OK" "$1"; fi
    draw 1
}

phase() {
    DETAIL1="$1" DETAIL2=""
    draw 1
}

stream() {
    local handler=$1 line buf="" rc=0 st
    shift
    while :; do
        if IFS= read -r -t 0.25 line; then
            line="$buf$line" buf=""
            if [[ "$line" == "@@rc "* ]]; then rc=${line#@@rc }; continue; fi
            "$handler" "$line"
            draw
        else
            st=$?
            if (( st > 128 )); then buf+="$line"; draw; continue; fi
            break
        fi
    done < <(set +e; trap - ERR; "$@" </dev/null 2>&1 | tee -a "$LOG" | tr '\r' '\n'; echo "@@rc ${PIPESTATUS[0]}")
    return "$rc"
}

h_none() { :; }

APT_N=0 APT_TOTAL=0
h_apt() {
    local f pct desc
    case "$1" in
        dlstatus:*)
            IFS=: read -r _ _ pct desc <<< "$1"
            pct=${pct%%[.,]*}
            PCT=$(( pct * 75 / 100 ))
            local b=$(( APT_TOTAL * pct / 100 ))
            speed_update "$b"
            transfer_lines "$b" "$APT_TOTAL" "$pct" "$APT_N ${T[packages]}"
            ;;
        pmstatus:*)
            IFS=: read -r _ f pct desc <<< "$1"
            pct=${pct%%[.,]*}
            PCT=$(( 75 + pct * 25 / 100 ))
            local bar
            mkbar bar "$pct" "$BAR_W"
            DETAIL1="${C_CYAN}${bar}${C_OFF}  $(printf '%3d' "$pct")%  ${T[unpack]} $f"
            DETAIL2=""
            ;;
    esac
}

h_git() {
    local re='^(Receiving objects|Resolving deltas):[[:space:]]+([0-9]+)%[[:space:]]+\(([0-9]+)/([0-9]+)\)(,[[:space:]]+([0-9.]+[[:space:]][KMG]?i?B))?([[:space:]]+\|[[:space:]]+([0-9.]+[[:space:]][KMG]?i?B/s))?'
    if [[ "$1" =~ $re ]]; then
        local what=${BASH_REMATCH[1]} pct=${BASH_REMATCH[2]} a=${BASH_REMATCH[3]} b=${BASH_REMATCH[4]} size=${BASH_REMATCH[6]} sp=${BASH_REMATCH[8]} bar
        mkbar bar "$pct" "$BAR_W"
        if [ "$what" = "Receiving objects" ]; then
            PCT=$(( pct * 85 / 100 ))
            DETAIL1="${C_CYAN}${bar}${C_OFF}  $(printf '%3d' "$pct")%  ${size//./$DEC}"
            DETAIL2="${C_DIM}${sp:+${sp//./$DEC} $G_DOT }${a} ${T[of]} ${b} ${T[objects]}${C_OFF}"
            GIT_SIZE=${size:-$GIT_SIZE}
        else
            PCT=$(( 85 + pct * 15 / 100 ))
            DETAIL1="${C_CYAN}${bar}${C_OFF}  $(printf '%3d' "$pct")%  ${T[deltas]}"
            DETAIL2="${C_DIM}${a} ${T[of]} ${b}${C_OFF}"
        fi
    elif [[ "$1" == remote:* ]]; then
        DETAIL1="${T[prepare]}"
    fi
}

PIP_N=0 PIP_TOTAL=0 PIP_DONE_N=0 PIP_DONE_B=0 PIP_CUR="" PIP_CUR_B=0 PIP_CUR_T=0 PIP_INSTALLING=0
size_to_bytes() {
    local _v=$2 _n _u _int _frac=0
    _n=${_v% *} _u=${_v#* }
    _int=${_n%%.*}
    [[ "$_n" == *.* ]] && _frac=${_n#*.} && _frac=${_frac:0:1}
    _int=$(( 10#${_int:-0} * 10 + 10#${_frac:-0} ))
    case "$_u" in
        GB) printf -v "$1" '%d' $(( _int * 100000000 )) ;;
        MB) printf -v "$1" '%d' $(( _int * 100000 )) ;;
        kB) printf -v "$1" '%d' $(( _int * 100 )) ;;
        *) printf -v "$1" '%d' $(( _int / 10 )) ;;
    esac
}

pip_finish_current() {
    if [ -n "$PIP_CUR" ]; then
        PIP_DONE_N=$(( PIP_DONE_N + 1 ))
        PIP_DONE_B=$(( PIP_DONE_B + PIP_CUR_T ))
        PIP_CUR="" PIP_CUR_B=0 PIP_CUR_T=0
    fi
}

pip_view() {
    local done=$(( PIP_DONE_B + PIP_CUR_B )) total=$PIP_TOTAL pct
    (( total < done )) && total=$done
    if (( total > 0 )); then pct=$(( done * 100 / total ))
    elif (( PIP_N > 0 )); then pct=$(( PIP_DONE_N * 100 / PIP_N ))
    else pct=0
    fi
    PCT=$(( 8 + pct * 80 / 100 ))
    speed_update "$done"
    local n=$(( PIP_DONE_N + 1 ))
    (( PIP_N > 0 && n > PIP_N )) && n=$PIP_N
    STEP_NOTE[3]="$n ${T[of]} $PIP_N ${T[packages]}"
    transfer_lines "$done" "$total" "$pct" "${PIP_CUR}"
}

h_pip() {
    local l=$1
    l="${l#"${l%%[![:space:]]*}"}"
    case "$l" in
        *.metadata\ *) ;;
        "Downloading "*|"Using cached "*)
            pip_finish_current
            local rest=${l#Downloading } size=""
            rest=${rest#Using cached }
            if [[ "$rest" =~ \(([0-9.]+\ [kMG]?B)\)$ ]]; then size_to_bytes size "${BASH_REMATCH[1]}"; fi
            rest=${rest%% *}
            rest=${rest##*/}
            PIP_CUR=${rest%%-[0-9]*}
            PIP_CUR_T=${size:-0}
            if [[ "$l" == "Using cached "* ]]; then PIP_CUR_B=$PIP_CUR_T; fi
            pip_view
            ;;
        "Progress "*" of "*)
            local a b
            read -r _ a _ b <<< "$l"
            PIP_CUR_B=$a PIP_CUR_T=$b
            pip_view
            ;;
        "Building wheel for "*)
            DETAIL2="${C_DIM}${T[build]} ${l#Building wheel for }${C_OFF}"
            ;;
        "Installing collected packages:"*)
            pip_finish_current
            PIP_INSTALLING=1
            PCT=90
            STEP_NOTE[3]="$PIP_N ${T[packages]}"
            DETAIL1="${T[installpy]} ($PIP_N)"
            DETAIL2=""
            ;;
    esac
}

die() {
    local msg=$1
    trap - ERR
    if (( CUR > 0 )) && [ "${STEP_STATE[CUR]}" = run ]; then
        STEP_STATE[CUR]=fail
        STEP_DUR[CUR]=$(( EPOCHSECONDS - STEP_T0[CUR] ))
        draw 1
    fi
    printf '\n%s[%s]%s %s\n' "$C_RED" "${T[error]}" "$C_OFF" "$msg" >&2
    if [ -s "$LOG" ]; then
        printf '\n   %s%s:%s\n' "$C_DIM" "${T[lastlog]}" "$C_OFF" >&2
        tail -n 12 "$LOG" | tr '\r' '\n' | grep -v '^Progress ' | tail -n 12 | sed "s/^/   ${C_DIM}${G_PIPE}${C_OFF} /" >&2 || true
        printf '\n   %s: %s\n' "${T[fulllog]}" "$LOG" >&2
    fi
    exit 1
}

on_err() { die "${T[stopped]} $CUR (${T[line]} $1)"; }
cleanup() { if [ "$TTY" = 1 ]; then printf '\033[?25h\033[?7h'; fi; }

[ "$EUID" -eq 0 ] || { echo "${T[root]}" >&2; exit 1; }
command -v apt-get >/dev/null 2>&1 || { echo "${T[debian]}" >&2; exit 1; }
export DEBIAN_FRONTEND=noninteractive

mkdir -p "$LOG_DIR"
chmod 750 "$LOG_DIR"
: > "$LOG"
chmod 640 "$LOG"
trap 'on_err $LINENO' ERR
trap cleanup EXIT
if [ "$TTY" = 1 ]; then printf '\033[?25l\033[?7l\n'; fi

step_begin 1
phase "${T[repair]}"
stream h_none dpkg --configure -a || true
phase "${T[index]}"
stream h_none apt-get update -q
APT_N=0 APT_TOTAL=0
while read -r _ _ size _; do
    APT_N=$(( APT_N + 1 ))
    APT_TOTAL=$(( APT_TOTAL + ${size:-0} ))
done < <(apt-get install -y -qq --no-install-recommends --print-uris "${PREREQS[@]}" 2>>"$LOG" | grep "^'" || true)
if (( APT_N == 0 )); then
    step_end "${T[present]}"
else
    fmt_bytes apt_size "$APT_TOTAL"
    if (( APT_N == 1 )); then apt_word=${T[package]}; else apt_word=${T[packages]}; fi
    STEP_NOTE[1]="$APT_N $apt_word $G_DOT $apt_size"
    stream h_apt apt-get install -y -q --no-install-recommends -o APT::Status-Fd=1 -o Dpkg::Use-Pty=0 "${PREREQS[@]}"
    step_end "$APT_N $apt_word $G_DOT $apt_size"
fi

step_begin 2
GIT_SIZE=""
git config --global --add safe.directory "$ATENA_DIR" >>"$LOG" 2>&1 || true
phase "${T[prepare]}"
if [ -d "$ATENA_DIR/.git" ]; then
    stream h_git env LC_ALL=C git -C "$ATENA_DIR" fetch --progress origin "$BRANCH"
    phase "${T[checkout]}"
    git -C "$ATENA_DIR" reset --hard --quiet "origin/$BRANCH" >>"$LOG" 2>&1
else
    rm -rf "$ATENA_DIR"
    stream h_git env LC_ALL=C git clone --progress --branch "$BRANCH" "$REPO_URL" "$ATENA_DIR"
fi
HEAD_SHORT=$(git -C "$ATENA_DIR" rev-parse --short HEAD)
step_end "$HEAD_SHORT${GIT_SIZE:+ $G_DOT ${GIT_SIZE//./$DEC}}"

step_begin 3
if [ ! -x "$VENV/bin/pip" ]; then
    phase "${T[venv]}"
    rm -rf "$VENV"
    python3 -m venv "$VENV" </dev/null >>"$LOG" 2>&1
fi
PCT=3
phase "${T[pip]}"
stream h_none "$VENV/bin/pip" install --disable-pip-version-check --no-input -q --upgrade pip
exec 9>"$VENV/.requirements.lock"
if ! flock -n 9; then
    phase "${T[lock]}"
    flock -w 1800 9
fi
want=$(sha1sum "$REQ" | cut -c1-40)
if [ "$(cat "$STAMP" 2>/dev/null || true)" = "$want" ] \
        && "$VENV/bin/python" -c "import fastapi, uvicorn, httpx, psutil, pam" >/dev/null 2>&1; then
    step_end "${T[present]}"
else
    PCT=5
    phase "${T[resolve]}"
    REPORT=$(mktemp)
    stream h_none "$VENV/bin/pip" install --disable-pip-version-check --no-input -q --dry-run --report "$REPORT" -r "$REQ"
    mapfile -t PIP_URLS < <(jq -r '.install[].download_info.url' "$REPORT" || true)
    rm -f "$REPORT"
    PIP_N=${#PIP_URLS[@]}
    phase "${T[sizes]} ($PIP_N ${T[packages]})"
    PIP_TOTAL=0
    if (( PIP_N > 0 )); then
        PIP_TOTAL=$(printf '%s\n' "${PIP_URLS[@]}" \
            | xargs -r -P 8 -n 1 sh -c 'curl -fsIL --proto "=https" --max-time 15 "$1" 2>/dev/null | tr -d "\r" | awk "tolower(\$1)==\"content-length:\"{n=\$2} END{print n+0}"' _ \
            | awk '{s+=$1} END{print s+0}')
    fi
    PCT=8
    fmt_bytes pip_size "$PIP_TOTAL"
    STEP_NOTE[3]="0 ${T[of]} $PIP_N ${T[packages]}"
    phase "${T[download]} $G_DOT $pip_size"
    stream h_pip "$VENV/bin/pip" install --disable-pip-version-check --no-input --progress-bar raw -r "$REQ"
    echo "$want" > "$STAMP.tmp"
    mv -f "$STAMP.tmp" "$STAMP"
    if (( PIP_N == 0 )); then step_end "${T[present]}"
    elif (( PIP_TOTAL > 0 )); then step_end "$PIP_N ${T[packages]} $G_DOT $pip_size"
    else step_end "$PIP_N ${T[packages]}"
    fi
fi
exec 9>&-

step_begin 4
phase "${T[config]}"
mkdir -p /etc/atena /var/lib/atena
touch /etc/atena/atena.env
chmod 700 /etc/atena
chmod 600 /etc/atena/atena.env
grep -q '^ATENA_UPDATE_BRANCH=' /etc/atena/atena.env || echo "ATENA_UPDATE_BRANCH=$BRANCH" >> /etc/atena/atena.env
grep -q '^ATENA_AUTO_UPDATE=' /etc/atena/atena.env || echo "ATENA_AUTO_UPDATE=1" >> /etc/atena/atena.env
getent group atena-admin >/dev/null || groupadd --system atena-admin
ADMINS=()
for candidate in "${SUDO_USER:-}" "$(getent passwd 1000 | cut -d: -f1)"; do
    if [ -n "$candidate" ] && [ "$candidate" != "root" ] && id "$candidate" >/dev/null 2>&1; then
        usermod -aG atena-admin "$candidate"
        [[ " ${ADMINS[*]} " == *" $candidate "* ]] || ADMINS+=("$candidate")
    fi
done
PCT=40
draw 1
pkill -f 'backend/wizard_server.py' >/dev/null 2>&1 || true
systemctl disable atena-updater.service >/dev/null 2>&1 || true
rm -f /etc/systemd/system/atena-updater.service
install -m 0644 "$ATENA_DIR/scripts/os/systemd/atena-supervisor.service" /etc/systemd/system/
install -m 0644 "$ATENA_DIR/scripts/os/systemd/atena-rollback.service" /etc/systemd/system/
PCT=60
draw 1
bash "$ATENA_DIR/scripts/os/prestart.sh" >>"$LOG" 2>&1
if (( ${#ADMINS[@]} > 0 )); then step_end "${T[admin_user]} ${ADMINS[*]}"; else step_end ""; fi

step_begin 5
phase "${T[start]}"
systemctl daemon-reload >>"$LOG" 2>&1
systemctl enable atena-supervisor.service >>"$LOG" 2>&1
systemctl reset-failed atena-supervisor.service >>"$LOG" 2>&1 || true
systemctl restart atena-supervisor.service >>"$LOG" 2>&1
WAIT_MAX=120
ok=0
for (( w = 0; w < WAIT_MAX * 4; w++ )); do
    if (( w % 4 == 0 )); then
        if curl -fs -o /dev/null --max-time 2 http://127.0.0.1/healthz; then ok=1; break; fi
        PCT=$(( w * 95 / (WAIT_MAX * 4) ))
        DETAIL1="${T[waiting]} $G_DOT $(( w / 4 )) s"
    fi
    draw
    sleep 0.25
done
if (( ok == 0 )); then
    journalctl -u atena-supervisor -n 40 --no-pager >>"$LOG" 2>&1 || true
    die "${T[noresp]}: journalctl -u atena-supervisor"
fi
step_end "${T[ready]}"
trap - ERR

IP=$(hostname -I 2>/dev/null | awk '{print $1}')
fmt_dur total_dur $(( EPOCHSECONDS - START ))
echo
echo -e "   ${C_GREEN}${G_OK}${C_OFF} ${T[done]} ${C_DIM}(${total_dur})${C_OFF}"
echo -e "   ${T[autonomy]}"
echo
echo -e "   ${T[monitor]}:  ${C_GREEN}http://${IP:-localhost}/${C_OFF}"
echo -e "   ${T[admin]}:  ${C_GREEN}http://${IP:-localhost}:8080/${C_OFF}"
echo -e "   ${T[live]}:  journalctl -fu atena-supervisor"
echo
