import io
import os
import zipfile

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, StreamingResponse

from features.rpa import releases

admin_routes = APIRouter(tags=["RPA"])
public_routes = APIRouter(tags=["RPA"])

_SKIP_DIRS = {"__pycache__", "build", "dist", ".venv", "tests"}
_KEEP = (".py", ".bat", ".sh", "requirements.txt")

# features/rpa -> features -> installer_wizard -> radice del progetto
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
ASSISTANT_DIR = os.path.join(_ROOT, "client_satellite", "windows_assistant")
BRIDGE_DIR = os.path.join(_ROOT, "client_satellite", "context_bridge")
BRIDGE_PREFIX = "controllo_remoto/"

README = r"""ATENA Assistente per Windows
============================

1. Estrai questa cartella in un percorso breve, ad esempio C:\ATENA (evita percorsi molto lunghi).
2. Fai doppio clic su Start_ATENA_Assistente.bat
   La prima volta prepara i componenti (1-3 minuti). Serve Python 3.10 o piu recente con "Add Python to PATH".
3. Nella finestra "Collega questo PC ad ATENA" scrivi il codice di 6 cifre che trovi nel pannello di ATENA:
   Funzionalita -> Nodi e server -> "+ Aggiungi un nodo".
4. Comparira una piccola sfera luminosa nell'angolo dello schermo: e ATENA.
   Di' "Atena..." oppure premi Ctrl+Alt+Spazio per parlarle, o cliccala per scriverle.

La cartella "controllo_remoto" contiene il vecchio ponte di contesto per il controllo remoto (facoltativo).
Il registro degli errori si trova in %APPDATA%\ATENA\assistant.log
"""

_BRIDGE_BAT = """@echo off
echo Inizializzazione ATENA Satellite Client...
python -m pip install -r requirements.txt --quiet
start python gui.py
exit
"""
_BRIDGE_SH = """#!/bin/bash
echo "Inizializzazione ATENA Satellite Client..."
pip install -r requirements.txt --quiet
python3 gui.py &
"""
_BRIDGE_REQS = "fastapi\nuvicorn\nuiautomation\nmss\ncryptography\ncustomtkinter\npydantic\nrequests\n"


def _add_tree(zf: zipfile.ZipFile, folder: str, prefix: str) -> None:
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.endswith(".egg-info")]
        for file in files:
            if file.endswith(_KEEP) and "setup_msi" not in file:
                path = os.path.join(root, file)
                zf.write(path, prefix + os.path.relpath(path, folder).replace(os.sep, "/"))


def _server_address(request: Request) -> str:
    """Indirizzo pubblico di ATENA (le API dei nodi non stanno sulla porta del pannello di amministrazione)."""
    try:
        from config import PUBLIC_PORT
    except ImportError:
        PUBLIC_PORT = 80
    host = request.url.hostname or ""
    if not host or host in ("localhost", "127.0.0.1", "::1"):
        return ""
    return f"http://{host}" + ("" if PUBLIC_PORT == 80 else f":{PUBLIC_PORT}")


def _generate_zip(server: str = "") -> io.BytesIO:
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        if os.path.isdir(ASSISTANT_DIR):
            _add_tree(zf, ASSISTANT_DIR, "")
            zf.writestr("LEGGIMI.txt", README.replace("\n", "\r\n"))
            if server:
                zf.writestr("server.txt", server)
        if os.path.isdir(BRIDGE_DIR):
            _add_tree(zf, BRIDGE_DIR, BRIDGE_PREFIX)
            zf.writestr(BRIDGE_PREFIX + "Start_ATENA_Client.bat", _BRIDGE_BAT)
            zf.writestr(BRIDGE_PREFIX + "Start_ATENA_Client.sh", _BRIDGE_SH)
            zf.writestr(BRIDGE_PREFIX + "requirements.txt", _BRIDGE_REQS)
    zip_buffer.seek(0)
    return zip_buffer


@admin_routes.get("/api/rpa/download-client")
@public_routes.get("/api/rpa/download-client")
async def download_client(request: Request, format: str = "exe"):
    if format != "zip":
        url = await releases.installer_url()
        if url:
            return RedirectResponse(url, status_code=302)
    if not os.path.isfile(os.path.join(ASSISTANT_DIR, "atena_assistant.py")):
        raise HTTPException(
            status_code=404,
            detail=f"Sorgenti dell'Assistente Windows non trovati in {ASSISTANT_DIR}. "
                   "Verifica che la cartella client_satellite/windows_assistant sia presente nell'installazione di ATENA.",
        )
    return StreamingResponse(
        _generate_zip(_server_address(request)),
        media_type="application/x-zip-compressed",
        headers={"Content-Disposition": "attachment; filename=ATENA_Assistente_Windows.zip"},
    )
