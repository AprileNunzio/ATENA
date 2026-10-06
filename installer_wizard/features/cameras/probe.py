import asyncio
import shutil
import subprocess
import time

from features.cameras import live, netguard

TIMEOUT = 12


def jpeg_size(data: bytes) -> tuple[int, int] | None:
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xC0, 0xC1, 0xC2):
            return int.from_bytes(data[i + 7:i + 9], "big"), int.from_bytes(data[i + 5:i + 7], "big")
        i += 2 + int.from_bytes(data[i + 2:i + 4], "big")
    return None


def grab(url: str) -> tuple[bytes, str]:
    exe = shutil.which("ffmpeg")
    if not exe:
        return b"", "ffmpeg non è installato"
    command = [exe, "-nostdin", "-loglevel", "error", *live.ffmpeg_input({"kind": "ip", "device": url}), "-frames:v", "1",
               "-f", "image2", "-c:v", "mjpeg", "pipe:1"]
    try:
        result = subprocess.run(command, capture_output=True, timeout=TIMEOUT, check=False)
    except subprocess.TimeoutExpired:
        return b"", "nessuna risposta entro il tempo limite"
    except OSError as exc:
        return b"", str(exc)
    return result.stdout, netguard.redact(result.stderr.decode("utf-8", "replace").strip()[-200:], url)


async def test(url: str) -> dict:
    if not netguard.lan_url(url):
        return {"ok": False, "error": "Sono ammesse solo telecamere nella rete locale (indirizzi privati)"}
    started = time.time()
    data, error = await asyncio.to_thread(grab, url)
    if not data:
        return {"ok": False, "error": error or "nessun fotogramma ricevuto", "hint": hint(error)}
    size = jpeg_size(data)
    return {"ok": True, "ms": int((time.time() - started) * 1000), "width": size[0] if size else None, "height": size[1] if size else None}


def hint(error: str) -> str:
    low = (error or "").lower()
    if "401" in low or "unauthorized" in low:
        return "Utente o password errati"
    if "404" in low or "not found" in low:
        return "Percorso del flusso errato: prova un'altra marca nei modelli"
    if "refused" in low:
        return "Porta chiusa: controlla l'indirizzo e che RTSP sia attivo sulla telecamera"
    if "timed out" in low or "tempo" in low:
        return "Nessuna risposta: controlla che la telecamera sia accesa e nella stessa rete"
    return ""
