import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Dict, Any

from sensor import ContextSensor

app = FastAPI(title="Atena Context Satellite")

class ContextResponse(BaseModel):
    status: str
    data: Dict[str, Any]

@app.exception_handler(Exception)
async def global_exception_handler(request, exc: Exception):
    return JSONResponse(status_code=500, content={"status": "error", "message": str(exc)})

@app.get("/api/v1/context/active-window", response_model=ContextResponse)
async def get_active_window():
    info = ContextSensor.get_active_window_info()
    return {"status": "success", "data": info}

@app.get("/api/v1/context/text", response_model=ContextResponse)
async def get_text_context():
    info = ContextSensor.get_active_window_info()
    text = ContextSensor.extract_text_from_active_window()
    return {
        "status": "success", 
        "data": {
            "window_title": info["title"],
            "application": info["class_name"],
            "extracted_text": text
        }
    }

@app.get("/api/v1/context/vision", response_model=ContextResponse)
async def get_vision_context():
    info = ContextSensor.get_active_window_info()
    b64_image = ContextSensor.capture_active_window_screenshot()
    return {
        "status": "success", 
        "data": {
            "window_title": info["title"],
            "application": info["class_name"],
            "screenshot_base64": b64_image
        }
    }

def start_satellite(host: str = "127.0.0.1", port: int = 19999):
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    start_satellite()
