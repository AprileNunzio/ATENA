#!/usr/bin/env bash
. "$(dirname "$0")/../lib.sh"

core_healthy() { curl -fsS --max-time 5 "$CORE_URL/health" >/dev/null 2>&1; }

CORE_USER=atena-core
UNIT_SRC="$ATENA_DIR/scripts/os/systemd/atena-core.service"
UNIT=/etc/systemd/system/atena-core.service
NATIVE_ENV="$ATENA_ETC/core-native.env"
RUN_MARK="$ATENA_STATE/.core-native-running"
DATA_DIRS=(db certs models projects)

native_env() {
    printf '%s\n' PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 "PYTHONPATH=$ATENA_DIR" \
        ATENA_ENV=production ATENA_HOST=0.0.0.0 ATENA_PORT=8443 QDRANT_HOST=127.0.0.1 \
        "ATENA_TTS_MODELS_DIR=$ATENA_DIR/data/models/tts" "BRAIN_ROUTES_PATH=$ATENA_STATE/brain/routes.json" \
        "OLLAMA_BASE_URL=$OLLAMA_URL"
}
native_active() { systemctl is-active --quiet atena-core 2>/dev/null; }

native_check() {
    same_content "$UNIT" < "$UNIT_SRC" || return 1
    same_content "$NATIVE_ENV" < <(native_env) || return 1
    [ "$(cat "$RUN_MARK" 2>/dev/null)" = "$(core_src_hash)" ] || return 1
    native_active && core_healthy
}

stop_containers() {
    command -v docker >/dev/null 2>&1 || return 0
    docker rm -f atena-core atena-qdrant atena-inference >/dev/null 2>&1 || true
}

stop_native() {
    [ -f "$UNIT" ] || return 0
    systemctl disable --now atena-core >/dev/null 2>&1 || true
    rm -f "$RUN_MARK"
}

prepare_native_data() {
    id "$CORE_USER" >/dev/null 2>&1 \
        || useradd --system --user-group --home-dir /nonexistent --no-create-home --shell /usr/sbin/nologin "$CORE_USER"
    local d
    install -d -m 0750 -o "$CORE_USER" -g "$CORE_USER" "$ATENA_DIR/data"
    for d in "${DATA_DIRS[@]}"; do
        install -d -m 0750 -o "$CORE_USER" -g "$CORE_USER" "$ATENA_DIR/data/$d"
        chown -R "$CORE_USER:$CORE_USER" "$ATENA_DIR/data/$d"
    done
    find "$ATENA_DIR/data" -maxdepth 1 -type f -exec chown "$CORE_USER:$CORE_USER" {} +
    install -d -m 0750 -g "$CORE_USER" "$ATENA_STATE/brain"
    chgrp "$CORE_USER" "$ATENA_STATE/brain"
    chmod 0750 "$ATENA_STATE/brain"
    command -v setfacl >/dev/null 2>&1 && setfacl -m "u:$CORE_USER:x" "$ATENA_STATE" 2>/dev/null || true
}

rollback_to_docker() {
    warn "Il core senza Docker non risponde: ultimi log"
    journalctl -u atena-core -n 40 --no-pager 2>&1 || true
    stop_native
    if command -v docker >/dev/null 2>&1 && docker image inspect atena-core:local >/dev/null 2>&1; then
        warn "Torno al core in Docker, che su questo computer era già installato"
        set_env ATENA_CORE_RUNTIME docker
        apply_docker
        return 0
    fi
    fail "Atena Core non risponde su $CORE_URL/health"
}

apply_native() {
    progress 10 "Preparazione del core senza Docker"
    ensure_secret
    prepare_native_data
    write_if_changed "$NATIVE_ENV" 0600 < <(native_env) || true
    if write_if_changed "$UNIT" < "$UNIT_SRC"; then systemctl daemon-reload; fi
    progress 30 "Spegnimento dei container non più necessari"
    stop_containers
    progress 45 "Avvio di Atena Core"
    systemctl enable atena-core >/dev/null 2>&1
    systemctl restart atena-core
    progress 60 "Attesa risposta di Atena Core"
    if ! wait_for 180 core_healthy; then
        rollback_to_docker
        return 0
    fi
    core_src_hash > "$RUN_MARK"
    info "$(curl -fsS "$CORE_URL/health" | jq -c '{status, version, active_agents}' 2>/dev/null)"
    progress 100 "Servizi operativi senza Docker"
}

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
    if native_core; then native_check; return; fi
    ! native_active || return 1
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
    if native_core; then apply_native; else apply_docker; fi
}

apply_docker() {
    progress 10 "Pulizia configurazioni precedenti"
    stop_native
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
