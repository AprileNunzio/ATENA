#!/usr/bin/env bash
. "$(dirname "$0")/../lib.sh"

NAME=atena-voicestudio
VOLUME=atena-voicestudio
PORT=3900
DEFAULT_IMAGE=ghcr.io/debpalash/voicestudio:0.5.6
IMAGE="${ATENA_VOICESTUDIO_IMAGE:-$DEFAULT_IMAGE}"
[[ "$IMAGE" =~ ^[a-z0-9][a-z0-9./_-]{0,120}:[A-Za-z0-9._-]{1,64}$ ]] || IMAGE=$DEFAULT_IMAGE
HEALTH="http://127.0.0.1:$PORT/.well-known/voicestudio-speech"

wanted() { [ "${ATENA_VOICESTUDIO:-0}" = "1" ] && [ "${ATENA_VOICESTUDIO_WHERE:-local}" != "remote" ]; }
have_docker() { command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; }
gpu_flags() { has_usable_gpu && docker info 2>/dev/null | grep -qi nvidia && echo "--gpus all" || true; }
signature() { printf '%s|%s|%s' "$IMAGE" "$(gpu_flags)" "$(printf '%s' "${ATENA_VOICESTUDIO_KEY:-}" | sha1sum | cut -c1-12)"; }
running_signature() { docker inspect -f '{{ index .Config.Labels "atena.signature" }}' "$NAME" 2>/dev/null || true; }
running() { [ "$(docker inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null)" = "true" ]; }
healthy() { curl -fsS --max-time 5 "$HEALTH" >/dev/null 2>&1; }

remove_container() {
    have_docker || return 0
    docker inspect "$NAME" >/dev/null 2>&1 || return 0
    docker rm -f "$NAME" >/dev/null
    info "Studio delle voci locale fermato: le voci create restano nel volume $VOLUME"
}

step_check() {
    if ! wanted; then
        ! have_docker || ! docker inspect "$NAME" >/dev/null 2>&1
        return
    fi
    have_docker && running && [ "$(running_signature)" = "$(signature)" ] && healthy
}

ensure_docker() {
    have_docker && return 0
    progress 8 "Installazione del motore container Docker"
    local installer
    installer=$(mktemp)
    retry 3 5 curl -fsSL https://get.docker.com -o "$installer"
    retry 2 10 sh "$installer" || { apt_heal; sh "$installer"; }
    rm -f "$installer"
    systemctl enable --now docker >/dev/null 2>&1 || true
    wait_for 60 docker info || fail "Docker non si è avviato"
}

ensure_key() {
    [ -n "${ATENA_VOICESTUDIO_KEY:-}" ] && return 0
    set_env ATENA_VOICESTUDIO_KEY "$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
}

step_apply() {
    if ! wanted; then
        remove_container
        progress 100 "Studio delle voci locale non attivo"
        return 0
    fi
    [ "$(uname -m)" = "x86_64" ] || fail "Lo Studio delle voci funziona solo su computer x86-64: installalo su un altro PC e scegli «Su un altro computer»"
    local free_gb
    free_gb=$(df -BG --output=avail /var/lib 2>/dev/null | tail -1 | tr -dc '0-9')
    [ "${free_gb:-0}" -ge 12 ] || fail "Servono almeno 12 GB liberi sul disco (ora ${free_gb:-0} GB)"
    ensure_docker
    ensure_key
    progress 20 "Scarico lo Studio delle voci (circa 6 GB, può richiedere molti minuti)"
    retry 3 20 docker pull -q "$IMAGE" >/dev/null
    if docker inspect "$NAME" >/dev/null 2>&1 && [ "$(running_signature)" != "$(signature)" ]; then
        docker rm -f "$NAME" >/dev/null
    fi
    if ! docker inspect "$NAME" >/dev/null 2>&1; then
        progress 60 "Avvio dello Studio delle voci"
        local flags
        flags=$(gpu_flags)
        # shellcheck disable=SC2086
        OMNIVOICE_API_KEY="$ATENA_VOICESTUDIO_KEY" docker run -d --name "$NAME" --restart unless-stopped $flags \
            --label "atena.signature=$(signature)" \
            -p "127.0.0.1:$PORT:$PORT" \
            -e OMNIVOICE_API_KEY -e OMNIVOICE_ANALYTICS_DISABLED=1 \
            -v "$VOLUME:/app/omnivoice_data" \
            "$IMAGE" >/dev/null
    elif ! running; then
        docker start "$NAME" >/dev/null
    fi
    progress 75 "Attendo che lo Studio delle voci sia pronto"
    wait_for 600 healthy || fail "Lo Studio delle voci non risponde: guarda «docker logs $NAME»"
    progress 100 "Studio delle voci pronto su questo computer$( [ -n "$(gpu_flags)" ] && echo ' con la scheda video' )"
}

step_main "$@"
