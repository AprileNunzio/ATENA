import os
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any

from server.config.env import settings
from server.features.remote_control.manager import RemoteComputerManager

router = APIRouter(prefix="/api/v1/computer-control", tags=["Computer Control"])

class ComputerPayload(BaseModel):
    name: str
    protocol: str
    ip: str = ""
    url: str = ""
    username: str = ""
    password: str = ""
    key_path: str = ""
    api_key: str = ""

def _get_config_path() -> str:
    return os.path.join(settings.DATA_DIR, "network_map.json")

def _read_config() -> Dict[str, Any]:
    path = _get_config_path()
    if not os.path.exists(path):
        return {"computers": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        raise HTTPException(status_code=500, detail="Impossibile leggere il file di configurazione.")

def _write_config(data: Dict[str, Any]) -> None:
    path = _get_config_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        raise HTTPException(status_code=500, detail="Impossibile salvare la configurazione.")

@router.get("/list")
async def list_computers():
    config = _read_config()
    return {"status": "success", "data": config.get("computers", {})}

@router.post("/add")
async def add_computer(payload: ComputerPayload):
    config = _read_config()
    name_upper = payload.name.upper()
    
    if name_upper in config.get("computers", {}):
        raise HTTPException(status_code=400, detail="Un PC con questo nome esiste già.")
        
    comp_data = {"protocol": payload.protocol}
    if payload.protocol in ["winrm", "ssh", "linux_ssh", "rhel_ssh", "mac_ssh", "bsd_ssh"]:
        comp_data.update({"ip": payload.ip, "username": payload.username})
        if payload.protocol == "winrm":
            comp_data["password"] = payload.password
        else:
            comp_data["key_path"] = payload.key_path
    elif payload.protocol == "rest":
        comp_data.update({"url": payload.url, "api_key": payload.api_key})
        
    config.setdefault("computers", {})[name_upper] = comp_data
    _write_config(config)
    return {"status": "success", "message": "PC aggiunto correttamente."}

@router.delete("/remove/{pc_name}")
async def remove_computer(pc_name: str):
    config = _read_config()
    name_upper = pc_name.upper()
    if name_upper not in config.get("computers", {}):
        raise HTTPException(status_code=404, detail="PC non trovato.")
        
    del config["computers"][name_upper]
    _write_config(config)
    return {"status": "success", "message": "PC rimosso."}

@router.post("/sync/{pc_name}")
async def sync_computer(pc_name: str):
    manager = RemoteComputerManager()
    result = await manager.dispatch_command(pc_name, "status")
    if result["status"] == "error":
        return {"status": "error", "message": result["message"]}
    return {"status": "success", "data": result.get("data", "Sincronizzazione completata.")}
