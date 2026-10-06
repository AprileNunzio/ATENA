#!/usr/bin/env bash
. "$(dirname "$0")/../lib.sh"

EAR=/opt/atena-ear
UNIT_SRC="$ATENA_DIR/scripts/os/systemd/atena-ear.service"
UNIT=/etc/systemd/system/atena-ear.service
EDIR="$ATENA_DIR/installer_wizard/features/ear"
CODE=("$EDIR/service.py" "$EDIR/stt.py" "$EDIR/learner.py" "$EDIR/enhance.py" "$EDIR/music.py"
      "$EDIR/wakeword.py" "$EDIR/voiceprint.py" "$EDIR/earconf.py" "$EDIR/tuning.py" "$EDIR/wakegain.py"
      "$EDIR/recorder.py" "$EDIR/reviewer.py" "$EDIR/review_metrics.py" "$ATENA_DIR/installer_wizard/features/biometrics/embeddings.py")
OWW_URL=https://github.com/dscripka/openWakeWord/releases/download/v0.5.1
OWW_FILES=(melspectrogram.onnx embedding_model.onnx)
WAKE_NAME="${ATENA_WAKEWORD_MODEL:-ehi_atena}"
[[ "$WAKE_NAME" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$ && "$WAKE_NAME" != *..* ]] || WAKE_NAME=ehi_atena
WAKE_FILE="$EAR/wakeword/$WAKE_NAME.onnx"
SPEAKER_URL=https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/wespeaker_en_voxceleb_resnet34_LM.onnx
SHERPA_VERSION=1.13.8

stt_model() {
    if [ -n "${ATENA_STT_MODEL:-}" ]; then echo "$ATENA_STT_MODEL"
    elif [ "$(nproc)" -ge 6 ] && grep -q avx2 /proc/cpuinfo; then echo small
    else echo base
    fi
}

wake_model() {
    if [ -n "${ATENA_WAKE_MODEL:-}" ]; then echo "$ATENA_WAKE_MODEL"
    elif [ "$(nproc)" -ge 6 ] && grep -q avx2 /proc/cpuinfo; then echo base
    else echo tiny
    fi
}

review_model() {
    case "${ATENA_EAR_REVIEW_MODEL:-same}" in
        base|small|medium) echo "${ATENA_EAR_REVIEW_MODEL}" ;;
        *) echo "" ;;
    esac
}

ear_enabled() { [ "${ATENA_EAR:-1}" != "0" ]; }
ear_ok() { timeout 3 bash -c 'exec 3<>/dev/tcp/127.0.0.1/8093' 2>/dev/null; }
py() { "$EAR/venv/bin/python" "$@"; }

model_cached() {
    local m
    for m in "$(stt_model)" "$(wake_model)" "$(review_model)"; do
        [ -z "$m" ] && continue
        [ -n "$(find "$EAR/models" -maxdepth 1 -type d -name "*faster-whisper-$m" 2>/dev/null)" ] || return 1
    done
}

wake_wanted() {
    case "${ATENA_WAKEWORD:-auto}" in
        0) return 1 ;;
        1) return 0 ;;
        *) ! commercial ;;
    esac
}

instant_ready() {
    local f
    wake_wanted || return 0
    [ -n "$(find "$EAR/.instant-unsupported" -mtime -1 2>/dev/null)" ] && return 0
    [ -s "$WAKE_FILE" ] || [ -n "${ATENA_WAKEWORD_URL:-}" ] || return 0
    py -c "import openwakeword" 2>/dev/null || return 1
    [ -s "$WAKE_FILE" ] || return 1
    for f in "${OWW_FILES[@]}"; do [ -s "$EAR/wakeword/$f" ] || return 1; done
}

fetch_wake_model() {
    local url="${ATENA_WAKEWORD_URL:-}" sum="${ATENA_WAKEWORD_SHA256:-}"
    [ -s "$WAKE_FILE" ] && return 0
    [ -n "$url" ] || return 1
    [[ "$url" == https://* ]] || { warn "ATENA_WAKEWORD_URL deve usare https://"; return 1; }
    [[ "${sum,,}" =~ ^[0-9a-f]{64}$ ]] || { warn "ATENA_WAKEWORD_SHA256 mancante o non valida: modello «Ehi, Atena» non scaricato"; return 1; }
    retry 3 5 curl -fsSL --proto =https --tlsv1.2 --max-filesize 20000000 -o "$WAKE_FILE.part" "$url" || { rm -f "$WAKE_FILE.part"; return 1; }
    if ! echo "${sum,,}  $WAKE_FILE.part" | sha256sum -c --status; then
        rm -f "$WAKE_FILE.part"
        warn "Il modello «Ehi, Atena» scaricato non corrisponde a ATENA_WAKEWORD_SHA256: scartato"
        return 1
    fi
    chmod 0644 "$WAKE_FILE.part"
    mv -f "$WAKE_FILE.part" "$WAKE_FILE"
}

voiceprint_ready() {
    [ "${ATENA_VOICEPRINT:-1}" = "0" ] && return 0
    [ -n "$(find "$EAR/.voiceprint-unsupported" -mtime -1 2>/dev/null)" ] && return 0
    py -c "import sherpa_onnx" 2>/dev/null && [ -s "$EAR/voiceprint/speaker.onnx" ]
}

install_instant() {
    local f
    mkdir -p "$EAR/wakeword"
    if ! py -c "import openwakeword" 2>/dev/null; then
        retry 3 5 "$EAR/venv/bin/pip" install -q onnxruntime requests tqdm scipy \
            && retry 3 5 "$EAR/venv/bin/pip" install -q --no-deps openwakeword || return 1
    fi
    for f in "${OWW_FILES[@]}"; do
        [ -s "$EAR/wakeword/$f" ] && continue
        retry 3 5 curl -fsSL -o "$EAR/wakeword/$f.part" "$OWW_URL/$f" || return 1
        mv -f "$EAR/wakeword/$f.part" "$EAR/wakeword/$f"
    done
    fetch_wake_model || return 1
    py -c "
from openwakeword.model import Model
Model(wakeword_models=['$WAKE_FILE'], inference_framework='onnx',
      melspec_model_path='$EAR/wakeword/melspectrogram.onnx', embedding_model_path='$EAR/wakeword/embedding_model.onnx')"
}

install_voiceprint() {
    mkdir -p "$EAR/voiceprint"
    if ! py -c "import sherpa_onnx" 2>/dev/null; then
        retry 3 5 "$EAR/venv/bin/pip" install -q "sherpa-onnx==$SHERPA_VERSION" "sherpa-onnx-core==$SHERPA_VERSION" || return 1
    fi
    if [ ! -s "$EAR/voiceprint/speaker.onnx" ]; then
        retry 3 10 curl -fsSL -o "$EAR/voiceprint/speaker.onnx.part" "$SPEAKER_URL" || return 1
        mv -f "$EAR/voiceprint/speaker.onnx.part" "$EAR/voiceprint/speaker.onnx"
    fi
    py -c "
import sherpa_onnx
sherpa_onnx.SpeakerEmbeddingExtractor(sherpa_onnx.SpeakerEmbeddingExtractorConfig(model='$EAR/voiceprint/speaker.onnx'))"
}

step_check() {
    if ! ear_enabled; then
        ! systemctl is-active --quiet atena-ear
        return
    fi
    py -c "import faster_whisper, websockets" 2>/dev/null || return 1
    model_cached && instant_ready && voiceprint_ready || return 1
    same_content "$UNIT" < "$UNIT_SRC" && systemctl is-enabled --quiet atena-ear && ear_ok \
        && code_current ear "${CODE[@]}"
}

step_apply() {
    if ! ear_enabled; then
        systemctl disable --now atena-ear >/dev/null 2>&1 || true
        progress 100 "Ascolto vocale disabilitato da configurazione"
        return 0
    fi
    mkdir -p "$EAR/models"
    progress 10 "Ambiente di riconoscimento vocale"
    [ -x "$EAR/venv/bin/python" ] || python3 -m venv "$EAR/venv"
    if ! py -c "import faster_whisper, websockets" 2>/dev/null; then
        retry 3 5 "$EAR/venv/bin/pip" install -q --upgrade pip
        retry 3 5 "$EAR/venv/bin/pip" install -q faster-whisper websockets
    fi

    local model
    model=$(stt_model)
    progress 35 "Download del modello di ascolto ($model)"
    retry 3 10 py -c "
from faster_whisper import WhisperModel
for m in {x for x in ('$model', '$(wake_model)', '$(review_model)') if x}:
    WhisperModel(m, device='cpu', compute_type='int8', download_root='$EAR/models')
print('modelli pronti')"

    progress 55 "Rilevatore istantaneo «Ehi, Atena»"
    if commercial; then
        if wake_wanted; then
            warn "I modelli di base di openWakeWord hanno licenza CC BY-NC-SA 4.0 (non commerciale): li installo perché ATENA_WAKEWORD=1"
        else
            info "Uso commerciale: i modelli di base di openWakeWord (CC BY-NC-SA 4.0) non si installano da soli; ATENA_WAKEWORD=1 per installarli comunque"
        fi
    fi
    if wake_wanted && [ ! -s "$WAKE_FILE" ] && [ -z "${ATENA_WAKEWORD_URL:-}" ]; then
        info "Modello «Ehi, Atena» non presente in $WAKE_FILE: l'attivazione usa il riconoscimento del parlato"
    elif wake_wanted && ! instant_ready; then
        if install_instant; then rm -f "$EAR/.instant-unsupported"
        else warn "Rilevatore istantaneo non supportato da questo hardware: resta l'attivazione con il parlato"
            touch "$EAR/.instant-unsupported"
        fi
    fi

    progress 70 "Riconoscimento della persona dalla voce"
    if [ "${ATENA_VOICEPRINT:-1}" != "0" ] && ! voiceprint_ready; then
        if install_voiceprint; then rm -f "$EAR/.voiceprint-unsupported"
        else warn "Impronta vocale non supportata da questo hardware: Atena riconoscerà le persone solo dal volto"
            touch "$EAR/.voiceprint-unsupported"
        fi
    fi
    mkdir -p /var/lib/atena/voiceprints
    chmod 700 /var/lib/atena/voiceprints

    progress 85 "Avvio del servizio di ascolto"
    if write_if_changed "$UNIT" < "$UNIT_SRC"; then systemctl daemon-reload; fi
    systemctl enable atena-ear >/dev/null 2>&1
    systemctl restart atena-ear
    wait_for 180 ear_ok || fail "Il servizio di ascolto non risponde"
    code_mark ear "${CODE[@]}"
    info "Ascolto vocale attivo (modello $model): dì \"Atena\" o \"Ehi, Atena\" seguito dalla richiesta"
    progress 100 "Ascolto vocale attivo"
}

step_main "$@"
