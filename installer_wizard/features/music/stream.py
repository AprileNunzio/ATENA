import logging
import re
import shutil
import subprocess
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from features.music import conf, layout

log = logging.getLogger("atena.music")
CHUNK = 128 * 1024
RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")


def parse_range(header: str | None, size: int) -> tuple[int, int] | None:
    if not header:
        return None
    match = RANGE.match(header.strip())
    if not match or (not match.group(1) and not match.group(2)):
        raise HTTPException(416, "Intervallo non valido")
    if match.group(1):
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) else size - 1
    else:
        start = max(0, size - int(match.group(2)))
        end = size - 1
    end = min(end, size - 1)
    if start > end or start >= size:
        raise HTTPException(416, "Intervallo non valido")
    return start, end


def chunks(path: Path, start: int, end: int):
    with open(path, "rb") as handle:
        handle.seek(start)
        left = end - start + 1
        while left > 0:
            data = handle.read(min(CHUNK, left))
            if not data:
                break
            left -= len(data)
            yield data


def ranged(path: Path, mime: str, request: Request, filename: str = "") -> Response:
    try:
        size = path.stat().st_size
    except OSError:
        raise HTTPException(404, "File non trovato")
    span = parse_range(request.headers.get("range"), size)
    headers = {"Accept-Ranges": "bytes", "Cache-Control": "private, max-age=3600"}
    if filename:
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    if span is None:
        headers["Content-Length"] = str(size)
        return StreamingResponse(chunks(path, 0, size - 1), media_type=mime, headers=headers)
    start, end = span
    headers.update({"Content-Range": f"bytes {start}-{end}/{size}", "Content-Length": str(end - start + 1)})
    return StreamingResponse(chunks(path, start, end), status_code=206, media_type=mime, headers=headers)


def ffmpeg() -> str | None:
    return shutil.which("ffmpeg")


def needs_transcode(path: Path, force: str = "") -> bool:
    mode = conf.transcode_mode()
    if force == "mp3":
        return True
    if mode == "never":
        return False
    return mode == "always" or path.suffix.lower() not in layout.BROWSER_SAFE


def transcoded(path: Path, kbps: int | None = None) -> Response:
    exe = ffmpeg()
    if not exe:
        raise HTTPException(415, "Formato non riproducibile e ffmpeg non installato")
    rate = f"{kbps or conf.transcode_kbps()}k"
    proc = subprocess.Popen([exe, "-v", "error", "-nostdin", "-i", str(path), "-vn", "-map_metadata", "-1", "-c:a", "libmp3lame",
                             "-b:a", rate, "-f", "mp3", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def pipe():
        try:
            while True:
                data = proc.stdout.read(CHUNK)
                if not data:
                    break
                yield data
        finally:
            proc.kill()
            proc.wait()

    return StreamingResponse(pipe(), media_type="audio/mpeg", headers={"Cache-Control": "no-store"})


def serve(path: Path, request: Request, fmt: str = "") -> Response:
    if not layout.inside(layout.root(), path) or not path.is_file():
        raise HTTPException(404, "Brano non trovato")
    if needs_transcode(path, fmt):
        if fmt == "mp3" or ffmpeg():
            return transcoded(path)
    return ranged(path, layout.mime(path.name), request)
