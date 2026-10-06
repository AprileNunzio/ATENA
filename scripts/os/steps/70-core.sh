#!/usr/bin/env bash
. "$(dirname "$0")/../lib.sh"

IMAGE=atena-core:local
CORE_VENV=/opt/atena-core/venv
NATIVE_MARK="$ATENA_STATE/.core-native"

image_hash() {
    docker image inspect "$IMAGE" --format '{{ index .Config.Labels "org.atena.src" }}' 2>/dev/null || true
}

gpu_profile() { [[ ",${COMPOSE_PROFILES:-}," == *",gpu,"* ]]; }

native_ready() {
    [ "$(cat "$NATIVE_MARK" 2>/dev/null)" = "$(core_src_hash)" ] \
        && "$CORE_VENV/bin/python" -c "import fastapi, uvicorn, pydantic_settings, sqlalchemy" 2>/dev/null
}

apply_native() {
    progress 10 "Ambiente Python del Core, senza Docker"
    [ -x "$CORE_VENV/bin/python" ] || python3 -m venv "$CORE_VENV" || fail "Ambiente Python del Core non creato"
    retry 3 5 "$CORE_VENV/bin/pip" install -q --disable-pip-version-check --upgrade pip
    progress 40 "Installazione delle librerie del Core"
    retry 3 5 "$CORE_VENV/bin/pip" install -q --disable-pip-version-check --require-virtualenv \
        -r "$ATENA_DIR/server/requirements.txt" || fail "Librerie del Core non installate"
    "$CORE_VENV/bin/python" -c "import fastapi, uvicorn, pydantic_settings, sqlalchemy" || fail "Librerie del Core incomplete"
    mkdir -p "$ATENA_STATE"
    core_src_hash > "$NATIVE_MARK"
    progress 100 "Core pronto senza Docker"
}

step_check() {
    if native_core; then native_ready; return; fi
    local want
    want=$(core_src_hash)
    [ -n "$want" ] && [ "$(image_hash)" = "$want" ] || return 1
    ! gpu_profile || docker image inspect atena-inference:local >/dev/null 2>&1
}

step_apply() {
    if native_core; then apply_native; return; fi
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
