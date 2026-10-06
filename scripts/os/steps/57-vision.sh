#!/usr/bin/env bash
. "$(dirname "$0")/../lib.sh"

MODELS=/opt/atena-vision/models
ZOO=https://github.com/opencv/opencv_zoo/raw/main/models
UNIT_SRC="$ATENA_DIR/scripts/os/systemd/atena-vision.service"
UNIT=/etc/systemd/system/atena-vision.service
VDIR="$ATENA_DIR/installer_wizard/features/vision"
BDIR="$ATENA_DIR/installer_wizard/features/biometrics"
CODE=("$VDIR/service.py" "$VDIR/gallery.py" "$VDIR/tracks.py" "$VDIR/objects.py" "$VDIR/devices.py"
      "$VDIR/ircam.py" "$VDIR/fusion.py" "$VDIR/learning.py" "$VDIR/selection.py" "$BDIR/embeddings.py" "$BDIR/liveness.py")
FILES=(
    "face_detection_yunet/face_detection_yunet_2023mar.onnx"
    "face_recognition_sface/face_recognition_sface_2021dec.onnx"
    "object_detection_nanodet/object_detection_nanodet_2022nov.onnx"
)

vision_enabled() { [ "${ATENA_VISION:-1}" != "0" ]; }
api_ok() { curl -fsS --max-time 5 http://127.0.0.1:8091/health >/dev/null 2>&1; }

step_check() {
    if ! vision_enabled; then
        ! systemctl is-active --quiet atena-vision
        return
    fi
    local f
    command -v v4l2-ctl >/dev/null 2>&1 || return 1
    for f in "${FILES[@]}"; do [ -s "$MODELS/${f##*/}" ] || return 1; done
    same_content "$UNIT" < "$UNIT_SRC" && systemctl is-enabled --quiet atena-vision && api_ok \
        && code_current vision "${CODE[@]}"
}

step_apply() {
    if ! vision_enabled; then
        systemctl disable --now atena-vision >/dev/null 2>&1 || true
        progress 100 "Visione disabilitata da configurazione"
        return 0
    fi
    mkdir -p "$MODELS" /var/lib/atena/faces
    command -v v4l2-ctl >/dev/null 2>&1 || apt_install v4l-utils || warn "v4l-utils non installato: le webcam a doppio sensore non saranno riconosciute"
    [ -d /sys/bus/usb/drivers/uvcvideo ] || modprobe uvcvideo >/dev/null 2>&1 || true
    chmod 700 /var/lib/atena/faces
    local i=0 f
    for f in "${FILES[@]}"; do
        i=$((i + 1))
        if [ ! -s "$MODELS/${f##*/}" ]; then
            progress $((i * 20)) "Download rete visiva ${f##*/}"
            retry 3 5 curl -fsSL -o "$MODELS/${f##*/}.part" "$ZOO/$f"
            mv -f "$MODELS/${f##*/}.part" "$MODELS/${f##*/}"
        fi
    done

    progress 70 "Avvio del servizio di visione"
    ls /dev/video* >/dev/null 2>&1 || warn "Nessuna webcam rilevata: il servizio attenderà il collegamento"
    if write_if_changed "$UNIT" < "$UNIT_SRC"; then systemctl daemon-reload; fi
    systemctl enable atena-vision >/dev/null 2>&1
    systemctl restart atena-vision
    wait_for 60 api_ok || fail "Il servizio di visione non risponde"
    code_mark vision "${CODE[@]}"
    info "Visione: $(curl -fsS http://127.0.0.1:8091/health)"
    progress 100 "Visione attiva"
}

step_main "$@"
