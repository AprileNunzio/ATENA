import json
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Dict, Any

from sensor import ContextSensor
from crypto import E2EEncryption
from updater import apply_update

app = FastAPI(title="Atena Context Satellite")

class EncryptedPayload(BaseModel):
    payload: str

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    err_json = json.dumps({"status": "error", "message": str(exc)})
    encrypted_err = E2EEncryption.encrypt_payload(err_json)
    return JSONResponse(status_code=500, content={"payload": encrypted_err})

@app.post("/api/v1/context/active-window", response_model=EncryptedPayload)
async def get_active_window():
    info = ContextSensor.get_active_window_info()
    enc = E2EEncryption.encrypt_payload(json.dumps({"status": "success", "data": info}))
    return {"payload": enc}

@app.post("/api/v1/context/text", response_model=EncryptedPayload)
async def get_text_context():
    info = ContextSensor.get_active_window_info()
    text = ContextSensor.extract_text_from_active_window()
    res = {
        "status": "success", 
        "data": {
            "window_title": info["title"],
            "application": info["class_name"],
            "extracted_text": text
        }
    }
    enc = E2EEncryption.encrypt_payload(json.dumps(res))
    return {"payload": enc}

@app.post("/api/v1/context/vision", response_model=EncryptedPayload)
async def get_vision_context():
    info = ContextSensor.get_active_window_info()
    b64_image = ContextSensor.capture_active_window_screenshot()
    res = {
        "status": "success", 
        "data": {
            "window_title": info["title"],
            "application": info["class_name"],
            "screenshot_base64": b64_image
        }
    }
    enc = E2EEncryption.encrypt_payload(json.dumps(res))
    return {"payload": enc}

@app.post("/api/v1/system/update", response_model=EncryptedPayload)
async def trigger_update(req: EncryptedPayload):
    decrypted = E2EEncryption.decrypt_payload(req.payload)
    cmd = json.loads(decrypted)
    download_url = cmd.get("download_url")
    if not download_url:
        raise ValueError("URL di download mancante.")
        
    res = {"status": "success", "message": "Aggiornamento in corso. Il satellite verrà riavviato."}
    enc = E2EEncryption.encrypt_payload(json.dumps(res))
    
    import threading
    threading.Thread(target=apply_update, args=(download_url,), daemon=True).start()
    
    return {"payload": enc}

def start_satellite(host: str = "127.0.0.1", port: int = 19999):
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    start_satellite()
