import base64
from typing import Dict, Any, Optional

def _ensure_deps():
    import importlib
    import subprocess
    import sys
    for pkg in ["uiautomation", "mss", "fastapi", "uvicorn"]:
        try:
            importlib.import_module(pkg)
        except ImportError:
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "--quiet"])
            importlib.invalidate_caches()

_ensure_deps()

import uiautomation as auto
import mss

class ContextSensor:
    @staticmethod
    def get_active_window_info() -> Dict[str, Any]:
        window = auto.GetForegroundControl()
        if not window:
            raise RuntimeError("Nessuna finestra attiva trovata.")
        
        return {
            "title": window.Name,
            "class_name": window.ClassName,
            "process_id": window.ProcessId,
            "bounding_rect": {
                "left": window.BoundingRectangle.left,
                "top": window.BoundingRectangle.top,
                "right": window.BoundingRectangle.right,
                "bottom": window.BoundingRectangle.bottom
            }
        }

    @staticmethod
    def extract_text_from_active_window() -> str:
        window = auto.GetForegroundControl()
        if not window:
            raise RuntimeError("Nessuna finestra attiva trovata.")
            
        texts = []
        for control, _ in auto.WalkControl(window, includeTop=True):
            if control.ControlType in (auto.ControlType.TextControl, auto.ControlType.DocumentControl, auto.ControlType.EditControl):
                val = control.Name or control.GetValuePattern().Value if auto.PatternId.ValuePattern in control.GetSupportedPatterns() else ""
                if val and val.strip():
                    texts.append(val.strip())
                    
        return "\n".join(texts)

    @staticmethod
    def capture_active_window_screenshot() -> str:
        window = auto.GetForegroundControl()
        if not window:
            raise RuntimeError("Nessuna finestra attiva trovata.")
            
        rect = window.BoundingRectangle
        monitor = {"top": rect.top, "left": rect.left, "width": rect.right - rect.left, "height": rect.bottom - rect.top}
        
        with mss.mss() as sct:
            sct_img = sct.grab(monitor)
            raw_bytes = mss.tools.to_png(sct_img.rgb, sct_img.size)
            return base64.b64encode(raw_bytes).decode('utf-8')
