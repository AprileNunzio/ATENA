#!/usr/bin/env bash
. "$(dirname "$0")/../lib.sh"

IMAGE=atena-core:local

image_hash() {
    docker image inspect "$IMAGE" --format '{{ index .Config.Labels "org.atena.src" }}' 2>/dev/null || true
}

gpu_profile() { [[ ",${COMPOSE_PROFILES:-}," == *",gpu,"* ]]; }

step_check() {
    local want
    want=$(core_src_hash)
    [ -n "$want" ] && [ "$(image_hash)" = "$want" ] || return 1
    ! gpu_profile || docker image inspect atena-inference:local >/dev/null 2>&1
}

step_apply() {
    export ATENA_SRC_HASH
    ATENA_SRC_HASH=$(core_src_hash)
    info "Versione sorgente Core: $ATENA_SRC_HASH"
    progress 3 "Preparazione build del Core"

    if ! compose --progress=plain build atena-core 2>&1 | while IFS= read -r line; do
        echo "$line"
        if [[ "$line" =~ \[([^]/]*\ )?([0-9]+)/([0-9]+)\]\ (.*) ]]; then
            progress $((5 + BASH_REMATCH[2] * 90 / BASH_REMATCH[3])) \
                "Build Core: fase ${BASH_REMATCH[2]} di ${BASH_REMATCH[3]}"
            detail "${BASH_REMATCH[4]:0:90}"
        elif [[ "$line" =~ Downloading\ ([^ ]+)\ \(([^\)]+)\) ]]; then
            detail "Download ${BASH_REMATCH[1]##*/} (${BASH_REMATCH[2]})"
        fi
    done; then
        fail "Build del Core non riuscita"
    fi

    if gpu_profile && ! docker image inspect atena-inference:local >/dev/null 2>&1; then
        progress 90 "Build del servizio di inferenza GPU"
        compose --progress=plain build atena-inference 2>&1 | tail -n 30 \
            || warn "Build dell'inferenza GPU non riuscita: il servizio resterà disattivato"
    fi

    progress 97 "Pulizia immagini obsolete"
    docker image prune -f >/dev/null 2>&1 || true
    [ "$(image_hash)" = "$ATENA_SRC_HASH" ] || fail "Immagine Core non coerente dopo la build"
    progress 100 "Atena Core compilato"
}

step_main "$@"
