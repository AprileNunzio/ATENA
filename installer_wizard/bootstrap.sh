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
        [retry]="Nuovo tentativo %d di %d" [heal_apt]="Gestore dei pacchetti riparato" [heal_net]="Connessione verificata"
        [heal_git]="Copia di Atena rimossa: la riscarico da zero" [heal_pipcache]="Cache delle librerie svuotata"
        [heal_venv]="Ambiente Python ricostruito da zero" [heal_repair]="Riparazione automatica eseguita" [autorepair]="Riparazione automatica"
        [disk_clean]="Pulizia del disco" [disk_full]="Spazio su disco insufficiente: liberi %s, ne servono almeno 2 GB. Libera spazio e rilancia il comando."
        [offline]="Nessuna connessione a internet: controlla cavo o Wi-Fi e rilancia il comando." [net_wait]="Nessuna connessione, riprovo"
        [net_check]="Verifica della connessione" [apt_wait]="Un altro programma sta installando pacchetti, attendo"
        [port_busy]="La porta %s è occupata dal programma «%s»: chiudilo o disinstallalo e rilancia il comando."
        [safe]="Atena è partita in modalità sicura e si sta riparando da sola: apri la pagina qui sotto per seguire la riparazione."
        [failed_after]="%s non riuscito dopo %d tentativi."
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
        [retry]="Retry %d of %d" [heal_apt]="Package manager repaired" [heal_net]="Connection checked"
        [heal_git]="Atena copy removed: downloading it again from scratch" [heal_pipcache]="Library cache cleared"
        [heal_venv]="Python environment rebuilt from scratch" [heal_repair]="Automatic repair done" [autorepair]="Automatic repair"
        [disk_clean]="Cleaning up the disk" [disk_full]="Not enough disk space: %s free, at least 2 GB needed. Free some space and run the command again."
        [offline]="No internet connection: check the cable or Wi-Fi and run the command again." [net_wait]="No connection, retrying"
        [net_check]="Checking the connection" [apt_wait]="Another program is installing packages, waiting"
        [port_busy]="Port %s is used by the program \"%s\": close or uninstall it and run the command again."
        [safe]="Atena started in safe mode and is repairing itself: open the page below to follow the repair."
        [failed_after]="%s failed after %d attempts."
    )
fi

TTY=0
if [ -t 1 ] && [ "${TERM:-dumb}" != dumb ]; then TTY=1; fi

FORCE_APT=0
for arg in "$@"; do
    if [ "$arg" = "--force-apt" ]; then FORCE_APT=1; fi
done

if [ "$(locale charmap 2>/dev/null || true)" = UTF-8 ]; then
    G_FULL="█" G_EMPTY="░" G_OK="✓" G_RUN="▶" G_WAIT="○" G_BAD="✗" G_DOT="·" G_SPIN=(⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧ ⠇ ⠏) G_PIPE="│"
else
    G_FULL="#" G_EMPTY="-" G_OK="+" G_RUN=">" G_WAIT="o" G_BAD="x" G_DOT="-" G_SPIN=("|" "/" "-" "\\") G_PIPE="|"
fi
if [ "$TTY" = 1 ]; then
    C_CYAN=$'\033[36m' C_GREEN=$'\033[32m' C_RED=$'\033[31m' C_AMBER=$'\033[33m' C_DIM=$'\033[2m' C_BOLD=$'\033[1m' C_OFF=$'\033[0m'
else
    C_CYAN="" C_GREEN="" C_RED="" C_AMBER="" C_DIM="" C_BOLD="" C_OFF=""
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

if [ "$EUID" -ne 0 ]; then
    if [ ! -t 0 ]; then
        echo -e "\033[31mERRORE: Lo script richiede i permessi di root.\033[0m" >&2
        echo "Stai eseguendo lo script via pipe. Se usassimo 'sudo' ora," >&2
        echo "la richiesta di password potrebbe inghiottire parte dello script." >&2
        echo "Per favore esegui il comando in questo modo:" >&2
        echo -e "\033[32m  curl -sL <URL> | sudo bash\033[0m" >&2
        exit 1
    fi
    echo -e "\033[33mQuesto script richiede i permessi di root. Richiesta sudo in corso...\033[0m" >&2
    exec sudo bash "$0" "$@"
    exit $?
fi
command -v apt-get >/dev/null 2>&1 || { echo "${T[debian]}" >&2; exit 1; }
export DEBIAN_FRONTEND=noninteractive

mkdir -p "$LOG_DIR"
chmod 750 "$LOG_DIR"
: > "$LOG"
chmod 640 "$LOG"
trap 'on_err $LINENO' ERR
trap cleanup EXIT
if [ "$TTY" = 1 ]; then printf '\033[?25l\033[?7l\n'; fi

MAX_TRY=3
HEAL_NOTE=""

pause() {
    local secs=$1 text=$2 k
    for (( k = secs * 4; k > 0; k-- )); do
        DETAIL1="${C_AMBER}${text} $G_DOT $(( (k + 3) / 4 )) s${C_OFF}"
        DETAIL2="${HEAL_NOTE:+${C_DIM}${HEAL_NOTE}${C_OFF}}"
        draw
        sleep 0.25
    done
}

attempt() {
    local fn=$1 heal=$2 i msg
    for (( i = 1; i <= MAX_TRY; i++ )); do
        if "$fn" "$i"; then return 0; fi
        (( i == MAX_TRY )) && break
        printf '\n--- %s: tentativo %d fallito, riparazione ---\n' "$fn" "$i" >> "$LOG"
        HEAL_NOTE=""
        DETAIL1="${C_AMBER}${T[autorepair]}${C_OFF}" DETAIL2=""
        draw 1
        "$heal" "$i" >>"$LOG" 2>&1 || true
        printf -v msg "${T[retry]}" $(( i + 1 )) "$MAX_TRY"
        pause $(( 5 * i * i )) "$msg"
    done
    printf -v msg "${T[failed_after]}" "${T[s$CUR]}" "$MAX_TRY"
    die "$msg"
}

free_mb() { df -Pm / | awk 'NR==2 {print $4+0}'; }
online() {
    curl -fsS --proto '=https' --max-time 8 -o /dev/null "${REPO_URL%.git}.git/info/refs?service=git-upload-pack" 2>/dev/null \
        || curl -fsS --proto '=https' --max-time 8 -o /dev/null https://pypi.org/simple/pip/ 2>/dev/null
}
apt_busy() { pgrep -x apt-get >/dev/null || pgrep -x apt >/dev/null || pgrep -x dpkg >/dev/null || pgrep -x unattended-upgr >/dev/null; }

wait_online() {
    local limit=${1:-300} t0=$EPOCHSECONDS restarted=0
    online && return 0
    while (( EPOCHSECONDS - t0 < limit )); do
        if (( restarted == 0 && EPOCHSECONDS - t0 >= 20 )); then
            systemctl restart systemd-resolved >>"$LOG" 2>&1 || true
            systemctl restart NetworkManager >>"$LOG" 2>&1 || true
            restarted=1
        fi
        DETAIL1="${C_AMBER}${T[net_wait]} $G_DOT $(( EPOCHSECONDS - t0 )) s${C_OFF}" DETAIL2=""
        draw 1
        sleep 4
        online && return 0
    done
    return 1
}

wait_apt() {
    local t0=$EPOCHSECONDS prompted=0 killed=0
    while apt_busy && (( EPOCHSECONDS - t0 < 1800 )); do
        if pgrep -x unattended-upgr >/dev/null; then
            if (( FORCE_APT )); then
                if (( killed == 0 )); then
                    systemctl stop unattended-upgrades 2>/dev/null || true
                    pkill -9 -x unattended-upgr || true
                    pkill -9 -x apt-get || true
                    pkill -9 -x apt || true
                    pkill -9 -x dpkg || true
                    rm -f /var/lib/dpkg/lock* /var/cache/apt/archives/lock*
                    dpkg --configure -a >>"$LOG" 2>&1 || true
                    killed=1
                    continue
                fi
            else
                if [ "$TTY" = 1 ] && (( prompted == 0 )); then
                    printf '\r\033[K\n%sAggiornamento automatico di Linux in corso, potrebbe richiedere minuti.%s\n' "$C_AMBER" "$C_OFF" >/dev/tty
                    printf 'Premi [Invio] se vuoi interromperlo forzatamente per installare Atena (o usa --force-apt)\n' >/dev/tty
                    prompted=1
                fi
                if (( prompted == 1 )); then
                    if read -r -t 3 </dev/tty; then
                        FORCE_APT=1
                        continue
                    fi
                else
                    sleep 3
                fi
            fi
        else
            sleep 3
        fi
        DETAIL1="${C_AMBER}${T[apt_wait]} $G_DOT $(( EPOCHSECONDS - t0 )) s${C_OFF}" DETAIL2=""
        draw 1
    done
}

heal_apt() {
    HEAL_NOTE=${T[heal_apt]}
    wait_apt
    dpkg --configure -a
    apt-get -f install -y -q
    (( $1 >= 2 )) && apt-get clean
    wait_online 120 || true
    return 0
}

heal_git() {
    HEAL_NOTE=${T[heal_net]}
    wait_online 180 || true
    if (( $1 >= 2 )); then
        rm -rf "$ATENA_DIR"
        HEAL_NOTE=${T[heal_git]}
    fi
    return 0
}

heal_pip() {
    wait_online 180 || true
    if (( $1 == 1 )); then
        "$VENV/bin/pip" cache purge
        rm -rf /root/.cache/pip
        HEAL_NOTE=${T[heal_pipcache]}
    else
        rm -rf "$VENV" /root/.cache/pip
        HEAL_NOTE=${T[heal_venv]}
    fi
    return 0
}

heal_none() { return 0; }

heal_start() {
    systemctl stop atena-supervisor.service
    bash "$ATENA_DIR/scripts/os/repair.sh" --quiet --no-restart --origin=installer
    HEAL_NOTE=${T[heal_repair]}
    return 0
}

do_prereqs() {
    local size
    if (( $1 == 1 )); then
        phase "${T[repair]}"
        stream h_none dpkg --configure -a || true
    fi
    phase "${T[index]}"
    stream h_none apt-get update -q || return 1
    APT_N=0 APT_TOTAL=0
    while read -r _ _ size _; do
        APT_N=$(( APT_N + 1 ))
        APT_TOTAL=$(( APT_TOTAL + ${size:-0} ))
    done < <(apt-get install -y -qq --no-install-recommends --print-uris "${PREREQS[@]}" 2>>"$LOG" | grep "^'" || true)
    if (( APT_N == 0 )); then
        apt-get install -y -qq --no-install-recommends "${PREREQS[@]}" </dev/null >>"$LOG" 2>&1 || return 1
        STEP_RESULT=${T[present]}
        return 0
    fi
    fmt_bytes apt_size "$APT_TOTAL"
    if (( APT_N == 1 )); then apt_word=${T[package]}; else apt_word=${T[packages]}; fi
    STEP_NOTE[1]="$APT_N $apt_word $G_DOT $apt_size"
    speed_reset
    stream h_apt apt-get install -y -q --no-install-recommends -o APT::Status-Fd=1 -o Dpkg::Use-Pty=0 "${PREREQS[@]}" || return 1
    STEP_RESULT="$APT_N $apt_word $G_DOT $apt_size"
}

do_download() {
    GIT_SIZE=""
    speed_reset
    phase "${T[prepare]}"
    if [ -d "$ATENA_DIR/.git" ] && git -C "$ATENA_DIR" rev-parse --verify -q HEAD >/dev/null 2>&1; then
        stream h_git env LC_ALL=C git -C "$ATENA_DIR" fetch --progress origin "$BRANCH" || return 1
        phase "${T[checkout]}"
        git -C "$ATENA_DIR" reset --hard --quiet "origin/$BRANCH" >>"$LOG" 2>&1 || return 1
    else
        rm -rf "$ATENA_DIR"
        stream h_git env LC_ALL=C git clone --progress --branch "$BRANCH" "$REPO_URL" "$ATENA_DIR" || return 1
    fi
    HEAD_SHORT=$(git -C "$ATENA_DIR" rev-parse --short HEAD) || return 1
    STEP_RESULT="$HEAD_SHORT${GIT_SIZE:+ $G_DOT ${GIT_SIZE//./$DEC}}"
}

do_python() {
    local want
    if [ ! -x "$VENV/bin/pip" ]; then
        phase "${T[venv]}"
        rm -rf "$VENV"
        python3 -m venv "$VENV" </dev/null >>"$LOG" 2>&1 || return 1
    fi
    PCT=3
    phase "${T[pip]}"
    stream h_none "$VENV/bin/pip" install --disable-pip-version-check --no-input -q --upgrade pip || return 1
    exec 9>"$VENV/.requirements.lock"
    if ! flock -n 9; then
        phase "${T[lock]}"
        flock -w 1800 9 || return 1
    fi
    want=$(sha1sum "$REQ" | cut -c1-40)
    if [ "$(cat "$STAMP" 2>/dev/null || true)" = "$want" ] \
            && "$VENV/bin/python" -c "import fastapi, uvicorn, httpx, psutil, pam" >/dev/null 2>&1; then
        exec 9>&-
        STEP_RESULT=${T[present]}
        return 0
    fi
    PCT=5
    phase "${T[resolve]}"
    REPORT=$(mktemp)
    stream h_none "$VENV/bin/pip" install --disable-pip-version-check --no-input -q --dry-run --report "$REPORT" -r "$REQ" || { rm -f "$REPORT"; exec 9>&-; return 1; }
    mapfile -t PIP_URLS < <(jq -r '.install[].download_info.url' "$REPORT" || true)
    rm -f "$REPORT"
    PIP_N=${#PIP_URLS[@]} PIP_DONE_N=0 PIP_DONE_B=0 PIP_CUR="" PIP_CUR_B=0 PIP_CUR_T=0
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
    speed_reset
    stream h_pip "$VENV/bin/pip" install --disable-pip-version-check --no-input --progress-bar raw -r "$REQ" || { exec 9>&-; return 1; }
    "$VENV/bin/python" -c "import fastapi, uvicorn, httpx, psutil, pam" >>"$LOG" 2>&1 || { exec 9>&-; return 1; }
    echo "$want" > "$STAMP.tmp" && mv -f "$STAMP.tmp" "$STAMP"
    exec 9>&-
    if (( PIP_N == 0 )); then STEP_RESULT=${T[present]}
    elif (( PIP_TOTAL > 0 )); then STEP_RESULT="$PIP_N ${T[packages]} $G_DOT $pip_size"
    else STEP_RESULT="$PIP_N ${T[packages]}"
    fi
}

do_config() {
    local candidate
    phase "${T[config]}"
    mkdir -p /etc/atena /var/lib/atena || return 1
    touch /etc/atena/atena.env
    chmod 700 /etc/atena
    chmod 600 /etc/atena/atena.env
    grep -q '^ATENA_UPDATE_BRANCH=' /etc/atena/atena.env || echo "ATENA_UPDATE_BRANCH=$BRANCH" >> /etc/atena/atena.env
    grep -q '^ATENA_AUTO_UPDATE=' /etc/atena/atena.env || echo "ATENA_AUTO_UPDATE=1" >> /etc/atena/atena.env
    getent group atena-admin >/dev/null || groupadd --system atena-admin || return 1
    ADMINS=()
    for candidate in "${SUDO_USER:-}" "$(getent passwd 1000 | cut -d: -f1)"; do
        if [ -n "$candidate" ] && [ "$candidate" != "root" ] && id "$candidate" >/dev/null 2>&1; then
            usermod -aG atena-admin "$candidate" || return 1
            [[ " ${ADMINS[*]} " == *" $candidate "* ]] || ADMINS+=("$candidate")
        fi
    done
    PCT=40
    draw 1
    pkill -f 'backend/wizard_server.py' >/dev/null 2>&1 || true
    systemctl disable atena-updater.service >/dev/null 2>&1 || true
    rm -f /etc/systemd/system/atena-updater.service
    install -m 0644 "$ATENA_DIR/scripts/os/systemd/atena-supervisor.service" /etc/systemd/system/ || return 1
    install -m 0644 "$ATENA_DIR/scripts/os/systemd/atena-rollback.service" /etc/systemd/system/ || return 1
    PCT=60
    draw 1
    bash "$ATENA_DIR/scripts/os/prestart.sh" >>"$LOG" 2>&1 || return 1
    if (( ${#ADMINS[@]} > 0 )); then STEP_RESULT="${T[admin_user]} ${ADMINS[*]}"; else STEP_RESULT=""; fi
}

port_owner() {
    ss -Hltnp "sport = :$1" 2>/dev/null | grep -o 'users:(("[^"]*",pid=[0-9]*' | head -n 1 | sed 's/users:(("\([^"]*\)",pid=\([0-9]*\)/\1 \2/'
}

check_ports() {
    local port owner name pid msg
    systemctl is-active -q atena-supervisor.service && return 0
    for port in 80 8080; do
        owner=$(port_owner "$port")
        [ -n "$owner" ] || continue
        read -r name pid <<< "$owner"
        if [ -n "$pid" ] && tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null | grep -q "$WIZ/"; then
            kill "$pid" 2>/dev/null || true
            continue
        fi
        printf -v msg "${T[port_busy]}" "$port" "$name"
        die "$msg"
    done
}

SAFE=0
do_start() {
    local w body
    phase "${T[start]}"
    check_ports
    systemctl daemon-reload >>"$LOG" 2>&1
    systemctl enable atena-supervisor.service >>"$LOG" 2>&1 || return 1
    systemctl reset-failed atena-supervisor.service >>"$LOG" 2>&1 || true
    systemctl restart atena-supervisor.service >>"$LOG" 2>&1 || return 1
    for (( w = 0; w < WAIT_MAX * 4; w++ )); do
        if (( w % 4 == 0 )); then
            if body=$(curl -fsS --max-time 2 http://127.0.0.1/healthz 2>/dev/null); then
                if jq -e '.safe_mode == true' >/dev/null 2>&1 <<< "$body"; then
                    (( $1 < MAX_TRY )) && return 1
                    SAFE=1
                fi
                STEP_RESULT=${T[ready]}
                return 0
            fi
            PCT=$(( w * 95 / (WAIT_MAX * 4) ))
            DETAIL1="${T[waiting]} $G_DOT $(( w / 4 )) s" DETAIL2=""
        fi
        draw
        sleep 0.25
    done
    journalctl -u atena-supervisor -n 40 --no-pager >>"$LOG" 2>&1 || true
    return 1
}

run_step() {
    local n=$1 fn=$2 heal=$3
    step_begin "$n"
    STEP_RESULT=""
    HEAL_NOTE=""
    attempt "$fn" "$heal"
    step_end "$STEP_RESULT"
}

preflight() {
    local mb shown
    mb=$(free_mb)
    if (( mb < 3072 )); then
        phase "${T[disk_clean]}"
        apt-get clean >>"$LOG" 2>&1 || true
        journalctl --vacuum-size=200M >>"$LOG" 2>&1 || true
        rm -rf /root/.cache/pip
        mb=$(free_mb)
        if (( mb < 2048 )); then
            fmt_bytes shown $(( mb * 1048576 ))
            printf -v shown "${T[disk_full]}" "$shown"
            die "$shown"
        fi
    fi
    phase "${T[net_check]}"
    wait_online 300 || die "${T[offline]}"
    wait_apt
}

WAIT_MAX=120
step_begin 1
preflight
STEP_RESULT=""
attempt do_prereqs heal_apt
step_end "$STEP_RESULT"
git config --global --add safe.directory "$ATENA_DIR" >>"$LOG" 2>&1 || true
run_step 2 do_download heal_git
run_step 3 do_python heal_pip
run_step 4 do_config heal_none
run_step 5 do_start heal_start
trap - ERR

IP=$(hostname -I 2>/dev/null | awk '{print $1}')
fmt_dur total_dur $(( EPOCHSECONDS - START ))
echo
if (( SAFE )); then
    echo -e "   ${C_AMBER}!${C_OFF} ${T[safe]}"
else
    echo -e "   ${C_GREEN}${G_OK}${C_OFF} ${T[done]} ${C_DIM}(${total_dur})${C_OFF}"
    echo -e "   ${T[autonomy]}"
fi
echo
echo -e "   ${T[monitor]}:  ${C_GREEN}http://${IP:-localhost}/${C_OFF}"
echo -e "   ${T[admin]}:  ${C_GREEN}http://${IP:-localhost}:8080/${C_OFF}"
echo -e "   ${T[live]}:  journalctl -fu atena-supervisor"
echo
