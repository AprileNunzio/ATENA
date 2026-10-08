import os
import io
import zipfile
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

admin_routes = APIRouter(tags=["RPA"])
public_routes = APIRouter(tags=["RPA"])

def _generate_zip():
    # Trova la cartella del satellite nel progetto
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../"))
    bridge_dir = os.path.join(project_root, "client_satellite", "context_bridge")
    
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # Aggiunge i file sorgente del client
        for root, _, files in os.walk(bridge_dir):
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
    zip_buffer = _generate_zip()
    return StreamingResponse(
        zip_buffer,
        media_type="application/x-zip-compressed",
        headers={"Content-Disposition": "attachment; filename=ATENA_Satellite_Client.zip"}
    )
