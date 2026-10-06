import asyncio
import hashlib
import io
import logging
import platform
import shutil
import subprocess
import tarfile
from pathlib import Path

import httpx

from features.vision import ir_configure
from state import store

log = logging.getLogger("atena.webcams")
VERSION = "6.1.2"
URL = ("https://github.com/EmixamPP/linux-enable-ir-emitter/releases/download/"
       f"{VERSION}/linux-enable-ir-emitter-{VERSION}-release.systemd.x86-64.tar.gz")
SHA256 = "f37e8a472df28a13d785373021dd92a51b48c014e528398631bc161e6282dc60"
MAX_BYTES = 20 * 1024 * 1024
ALLOWED_ROOTS = ("usr", "etc", "lib", "opt", "var")
SERVICE = "linux-enable-ir-emitter"
CONFIG_DIRS = (Path("/etc/linux-enable-ir-emitter"), Path("/etc/linux-enable-ir-emitter.d"))
state = {"busy": False, "last": ""}


def tool_path() -> str | None:
    return shutil.which("linux-enable-ir-emitter") or (
        "/usr/local/bin/linux-enable-ir-emitter" if Path("/usr/local/bin/linux-enable-ir-emitter").exists() else None)


def configured(dirs: tuple = CONFIG_DIRS) -> bool:
    for d in dirs:
        try:
            if d.is_dir() and any(d.iterdir()):
                return True
        except OSError:
            continue
    return False


def service_active() -> bool:
    exe = shutil.which("systemctl")
    if not exe:
        return False
    return subprocess.run([exe, "is-active", "--quiet", SERVICE], check=False).returncode == 0


def command_hint(ir_device: str | None, mode: dict | None) -> str:
    cmd = f"sudo linux-enable-ir-emitter --device {ir_device or '/dev/video2'}"
    if mode and mode.get("width") and mode.get("height"):
        cmd += f" --width {mode['width']} --height {mode['height']}"
    return cmd + " configure --no-gui"


def status(ir_device: str | None = None, mode: dict | None = None) -> dict:
    tool = tool_path()
    return {"supported_arch": platform.machine() in ("x86_64", "AMD64"), "tool": bool(tool), "version": VERSION,
            "configured": configured(), "service": service_active(), "busy": state["busy"], "last": state["last"],
            "command": command_hint(ir_device, mode), "session": ir_configure.view(), "auto": ir_auto_view()}


def ir_auto_view() -> dict:
    from features.vision import ir_auto
    return ir_auto.view()


def safe_members(tar: tarfile.TarFile) -> list[tarfile.TarInfo]:
    members = []
    for m in tar.getmembers():
        parts = Path(m.name).parts
        if m.name.startswith("/") or ".." in parts:
            raise ValueError(f"percorso non sicuro nell'archivio: {m.name}")
        if not (m.isfile() or m.isdir() or m.issym()):
            raise ValueError(f"tipo di file non ammesso nell'archivio: {m.name}")
        if parts and parts[0] not in ALLOWED_ROOTS and m.name not in (".", "./"):
            raise ValueError(f"cartella non prevista nell'archivio: {m.name}")
        members.append(m)
    return members


def verify_and_extract(data: bytes, root: Path = Path("/"), sha: str = SHA256) -> int:
    digest = hashlib.sha256(data).hexdigest()
    if digest != sha:
        raise ValueError(f"impronta del file non corrisponde (attesa {sha[:12]}…, ricevuta {digest[:12]}…)")
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        members = [m for m in safe_members(tar) if m.name not in (".", "./")]
        if hasattr(tarfile, "data_filter"):
            tar.extractall(root, members=members, filter="data")
        else:
            tar.extractall(root, members=members)
    return len(members)


async def download() -> bytes:
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        async with client.stream("GET", URL) as r:
            r.raise_for_status()
            chunks, size = [], 0
            async for chunk in r.aiter_bytes():
                size += len(chunk)
                if size > MAX_BYTES:
                    raise ValueError("file troppo grande")
                chunks.append(chunk)
    return b"".join(chunks)


async def install() -> dict:
    if state["busy"]:
        raise RuntimeError("Installazione già in corso")
    if platform.machine() not in ("x86_64", "AMD64"):
        raise RuntimeError("Lo strumento è disponibile solo per processori x86-64")
    state.update(busy=True, last="download in corso")
    try:
        data = await download()
        count = await asyncio.to_thread(verify_and_extract, data)
        exe = shutil.which("systemctl")
        if exe:
            await asyncio.to_thread(subprocess.run, [exe, "daemon-reload"], check=False)
        state["last"] = f"installato ({count} file, versione {VERSION})"
        store.event("INFO", f"Strumento per l'emettitore infrarosso {VERSION} installato", "vision")
    except (httpx.HTTPError, ValueError, OSError, tarfile.TarError) as exc:
        state["last"] = f"installazione non riuscita: {exc}"
        store.event("WARN", f"Strumento emettitore infrarosso: {exc}", "vision")
        raise
    finally:
        state["busy"] = False
    return status()


async def enable_service() -> dict:
    if not tool_path():
        raise RuntimeError("Lo strumento non è installato")
    if not configured():
        raise RuntimeError("Prima va configurato: esegui il comando mostrato sul server")
    exe = shutil.which("systemctl")
    if not exe:
        raise RuntimeError("systemctl non disponibile")
    result = await asyncio.to_thread(subprocess.run, [exe, "enable", "--now", SERVICE], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip()[:200] or "attivazione non riuscita")
    store.event("INFO", "Emettitore infrarosso attivato a ogni avvio", "vision")
    return status()
