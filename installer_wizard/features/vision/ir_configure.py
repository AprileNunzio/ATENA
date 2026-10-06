import asyncio
import logging
import os
import re
import shutil
import signal
import subprocess
import time
from pathlib import Path

from state import store

log = logging.getLogger("atena.webcams")
VISION_UNIT = "atena-vision"
MAX_SECONDS = 600
KEEP_CHARS = 4000
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\r")
ANSWERS = {"y": b"y\n", "n": b"n\n"}
session = {"running": False, "output": "", "started": 0.0, "result": "", "device": ""}
handle: dict = {"proc": None, "fd": None, "paused": False, "after": None, "responder": None}


def arguments(tool: str, device: str, mode: dict | None) -> list[str]:
    cmd = [tool, "--device", device]
    if mode and mode.get("width") and mode.get("height"):
        cmd += ["--width", str(mode["width"]), "--height", str(mode["height"])]
    return cmd + ["configure", "--no-gui"]


def clean(raw: bytes) -> str:
    return ANSI.sub("", raw.decode("utf-8", errors="replace"))


def systemctl(*args: str) -> None:
    exe = shutil.which("systemctl")
    if exe:
        subprocess.run([exe, *args], check=False, capture_output=True, timeout=30)


def valid_device(device: str) -> bool:
    return bool(re.fullmatch(r"/dev/video\d{1,3}", device or "")) and Path(device).exists()


def view() -> dict:
    return {**session, "output": session["output"][-KEEP_CHARS:], "elapsed": round(time.time() - session["started"]) if session["running"] else 0}


async def pump(fd: int, proc: asyncio.subprocess.Process) -> None:
    loop = asyncio.get_running_loop()
    deadline = time.time() + MAX_SECONDS
    while time.time() < deadline:
        try:
            chunk = await loop.run_in_executor(None, wait_read, fd)
        except OSError:
            break
        if chunk is None:
            if proc.returncode is not None:
                break
            continue
        if not chunk:
            break
        session["output"] = (session["output"] + clean(chunk))[-KEEP_CHARS * 2:]
        responder = handle["responder"]
        choice = responder(session["output"]) if responder else None
        if choice:
            try:
                answer(choice)
            except (RuntimeError, ValueError, OSError):
                pass
    await finish(proc)


def wait_read(fd: int) -> bytes | None:
    import select
    ready, _, _ = select.select([fd], [], [], 1.0)
    return os.read(fd, 4096) if ready else None


async def finish(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is None:
        proc.kill()
    code = await proc.wait()
    fd = handle["fd"]
    handle.update(proc=None, fd=None, responder=None)
    if fd is not None:
        try:
            os.close(fd)
        except OSError:
            pass
    session["running"] = False
    session["result"] = "completata" if code == 0 else f"terminata (codice {code})"
    if handle["paused"]:
        handle["paused"] = False
        await asyncio.to_thread(systemctl, "start", VISION_UNIT)
    store.event("INFO", f"Configurazione dell'emettitore infrarosso {session['result']}", "vision")
    after, handle["after"] = handle["after"], None
    if code == 0 and after is not None:
        try:
            await after()
            session["result"] += ": attivato a ogni avvio"
        except RuntimeError as exc:
            session["result"] += f": {exc}"


async def start(tool: str, device: str, mode: dict | None, after=None, responder=None) -> dict:
    import pty
    if session["running"]:
        raise RuntimeError("Configurazione già in corso")
    if not valid_device(device):
        raise RuntimeError("Sensore infrarosso non trovato: collega la webcam e riesamina")
    await asyncio.to_thread(systemctl, "stop", VISION_UNIT)
    handle["paused"] = True
    master, slave = pty.openpty()
    try:
        proc = await asyncio.create_subprocess_exec(*arguments(tool, device, mode), stdin=slave, stdout=slave, stderr=slave,
                                                    start_new_session=True)
    except OSError as exc:
        os.close(master)
        os.close(slave)
        handle["paused"] = False
        await asyncio.to_thread(systemctl, "start", VISION_UNIT)
        raise RuntimeError(f"Impossibile avviare lo strumento: {exc}")
    os.close(slave)
    handle.update(proc=proc, fd=master, after=after, responder=responder)
    session.update(running=True, output="", started=time.time(), result="", device=device)
    asyncio.create_task(pump(master, proc))
    store.event("INFO", f"Configurazione guidata dell'emettitore infrarosso avviata su {device}", "vision")
    return view()


def answer(choice: str) -> dict:
    data = ANSWERS.get(choice)
    if not session["running"] or handle["fd"] is None:
        raise RuntimeError("Nessuna configurazione in corso")
    if data is None:
        raise ValueError("Risposta non valida")
    os.write(handle["fd"], data)
    session["output"] += f"\n> {choice.upper()}\n"
    return view()


def cancel() -> dict:
    proc = handle["proc"]
    if proc is not None and proc.returncode is None:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            proc.kill()
    return view()
