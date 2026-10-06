#!/usr/bin/env bash
. "$(dirname "$0")/../lib.sh"

MUSIC=/opt/atena-music

id_wanted() {
    unofficial_ok || return 1
    [ "${ATENA_MUSIC_IDENTIFY:-1}" != "0" ] || { [ "${ATENA_MUSIC_ID:-1}" != "0" ] && [ "${ATENA_EAR:-1}" != "0" ]; }
}
cast_wanted() { [ "${ATENA_MUSIC_CAST:-1}" != "0" ]; }
id_ready() { "$MUSIC/venv/bin/python" -c "import shazamio" 2>/dev/null; }
cast_ready() { "$MUSIC/venv/bin/python" -c "import pychromecast" 2>/dev/null; }
cast_tried() { [ -f "$MUSIC/.cast-tried" ]; }

step_check() {
    if id_wanted && ! id_ready; then return 1; fi
    if cast_wanted && ! cast_ready && ! cast_tried; then return 1; fi
    return 0
}

step_apply() {
    if ! id_wanted && ! cast_wanted; then
        progress 100 "Riconoscimento musicale e Chromecast disattivati"
        return 0
    fi
    progress 15 "Ambiente per la musica"
    mkdir -p "$MUSIC"
    [ -x "$MUSIC/venv/bin/python" ] || python3 -m venv "$MUSIC/venv"
    retry 3 5 "$MUSIC/venv/bin/pip" install -q --upgrade pip
    if id_wanted; then
        progress 40 "Installazione del riconoscimento dei brani"
        retry 3 10 "$MUSIC/venv/bin/pip" install -q --prefer-binary --upgrade shazamio "audioop-lts; python_version >= '3.13'" \
            || fail "Libreria di riconoscimento musicale non installata"
        if ! id_ready; then
            warn "Import non riuscito:"
            "$MUSIC/venv/bin/python" -c "import shazamio" 2>&1 | tail -n 5
            fail "Riconoscimento musicale non funzionante"
        fi
    fi
    if cast_wanted; then
        progress 75 "Installazione del supporto Chromecast"
        if ! cast_ready; then
            retry 2 10 "$MUSIC/venv/bin/pip" install -q --prefer-binary --upgrade pychromecast || warn "Supporto Chromecast non installato"
        fi
        touch "$MUSIC/.cast-tried"
        cast_ready || warn "Chromecast non disponibile: la musica resta riproducibile su schermi, DLNA e browser"
    fi
    progress 100 "Musica pronta"
}

step_main "$@"
