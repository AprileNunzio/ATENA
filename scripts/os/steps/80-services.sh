#!/usr/bin/env bash
. "$(dirname "$0")/../lib.sh"

core_healthy() { curl -fsS --max-time 5 "$CORE_URL/health" >/dev/null 2>&1; }

running() {
    [ "$(docker inspect -f '{{.State.Running}}' "$1" 2>/dev/null)" = "true" ]
}

up_to_date() {
    local service=$1 want_hash have_hash
    want_hash=$(ATENA_SRC_HASH=$(core_src_hash) compose config --hash "$service" 2>/dev/null | awk '{print $2}')
    have_hash=$(docker inspect -f '{{ index .Config.Labels "com.docker.compose.config-hash" }}' "$service" 2>/dev/null)
    [ -n "$want_hash" ] && [ "$want_hash" = "$have_hash" ] || return 1
    if [ "$service" = atena-core ]; then
        [ "$(docker inspect -f '{{.Image}}' atena-core 2>/dev/null)" = \
          "$(docker image inspect -f '{{.Id}}' atena-core:local 2>/dev/null)" ] || return 1
    fi
}

ensure_secret() {
    [ -n "${ATENA_SECRET_KEY:-}" ] && [ -n "${ATENA_SECRET_KEY//0/}" ] && return 0
    set_env ATENA_SECRET_KEY "$(openssl rand -hex 32 2>/dev/null || python3 -c 'import secrets; print(secrets.token_hex(32))')"
    info "Chiave segreta del Core generata"
}

step_check() {
    [ -n "${ATENA_SECRET_KEY:-}" ] && [ -n "${ATENA_SECRET_KEY//0/}" ] || return 1
    running atena-core && running atena-qdrant \
        && up_to_date atena-core && up_to_date atena-qdrant \
        && core_healthy
}

remove_foreign_containers() {
    local c project
    for c in atena-core atena-qdrant atena-inference; do
        project=$(docker inspect -f '{{ index .Config.Labels "com.docker.compose.project" }}' "$c" 2>/dev/null || true)
        if [ -n "$project" ] && [ "$project" != "atena" ]; then
            warn "Rimozione container legacy $c (progetto '$project')"
            docker rm -f "$c" >/dev/null 2>&1 || true
        fi
    done
}

step_apply() {
    progress 10 "Pulizia configurazioni precedenti"
    ensure_secret
    remove_foreign_containers
    [ -d /etc/timezone ] && rmdir /etc/timezone 2>/dev/null || true
    mkdir -p "$ATENA_DIR/data/db" "$ATENA_DIR/data/certs" "$ATENA_DIR/data/qdrant" "$ATENA_DIR/data/models"

    progress 30 "Avvio servizi container"
    export ATENA_SRC_HASH
    ATENA_SRC_HASH=$(core_src_hash)
    retry 3 5 compose up -d --remove-orphans --no-build atena-qdrant atena-core
    if [[ ",${COMPOSE_PROFILES:-}," == *",gpu,"* ]]; then
        if docker image inspect atena-inference:local >/dev/null 2>&1; then
            compose up -d --no-build atena-inference || warn "Inferenza GPU non avviata: Atena prosegue su CPU"
        else
            warn "Immagine di inferenza GPU assente: servizio opzionale saltato"
        fi
    else
        docker rm -f atena-inference >/dev/null 2>&1 || true
    fi

    progress 60 "Attesa risposta di Atena Core"
    if ! wait_for 180 core_healthy; then
        warn "Atena Core non risponde: ultimi log"
        docker logs --tail 40 atena-core 2>&1 || true
        fail "Atena Core non risponde su $CORE_URL/health"
    fi
    info "$(curl -fsS "$CORE_URL/health" | jq -c '{status, version, active_agents}' 2>/dev/null)"
    progress 100 "Servizi operativi"
}

step_main "$@"
