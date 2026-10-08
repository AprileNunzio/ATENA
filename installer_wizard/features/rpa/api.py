import os
import io
import zipfile
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

admin_routes = APIRouter(tags=["RPA"])
public_routes = APIRouter(tags=["RPA"])

_SKIP_DIRS = {"__pycache__", "build", "dist"}


def _bridge_dir():
    # features/rpa -> features -> installer_wizard -> radice del progetto
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    return os.path.join(project_root, "client_satellite", "context_bridge")


def _generate_zip(bridge_dir):
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # Aggiunge i file sorgente del client
        for root, dirs, files in os.walk(bridge_dir):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.endswith(".egg-info")]
            for file in files:
                if file.endswith((".py", ".bat", ".sh", "requirements.txt")) and "setup_msi" not in file:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, bridge_dir)
                    zf.write(file_path, arcname)
                    
        # Crea uno script di avvio rapido per Windows
        bat_content = """@echo off
echo Inizializzazione ATENA Satellite Client...
python -m pip install -r requirements.txt --quiet
start python gui.py
exit
"""
        zf.writestr("Start_ATENA_Client.bat", bat_content)
        
        # Script per Linux/Mac
        sh_content = """#!/bin/bash
echo "Inizializzazione ATENA Satellite Client..."
pip install -r requirements.txt --quiet
python3 gui.py &
"""
        zf.writestr("Start_ATENA_Client.sh", sh_content)
        
        # Requisiti
        reqs = "fastapi\nuvicorn\nuiautomation\nmss\ncryptography\ncustomtkinter\npydantic\nrequests\n"
        zf.writestr("requirements.txt", reqs)

    zip_buffer.seek(0)
    return zip_buffer

@admin_routes.get("/api/rpa/download-client")
@public_routes.get("/api/rpa/download-client")
async def download_client_zip():
    bridge_dir = _bridge_dir()
    if not os.path.isfile(os.path.join(bridge_dir, "gui.py")):
        raise HTTPException(
            status_code=404,
            detail=f"Sorgenti del Client Satellite non trovati in {bridge_dir}. "
                   "Verifica che la cartella client_satellite/context_bridge sia presente nell'installazione di ATENA.",
        )
    zip_buffer = _generate_zip(bridge_dir)
    return StreamingResponse(
        zip_buffer,
        media_type="application/x-zip-compressed",
        headers={"Content-Disposition": "attachment; filename=ATENA_Satellite_Client.zip"}
    )
