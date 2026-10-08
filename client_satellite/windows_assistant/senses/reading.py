import logging
import time

import uiautomation as auto
from comtypes import COMError

from senses.windows import Window

log = logging.getLogger("atena.senses")
TEXT_KINDS = (auto.ControlType.DocumentControl, auto.ControlType.EditControl)


def _control_text(control, limit: int) -> str:
    pattern = control.GetPattern(auto.PatternId.TextPattern)
    if pattern:
        text = pattern.DocumentRange.GetText(limit)
        if text and text.strip():
            return text.strip()
    pattern = control.GetPattern(auto.PatternId.ValuePattern)
    return (pattern.Value or "").strip() if pattern else ""


def window_text(window: Window, limit: int = 20000, budget: float = 3.0) -> str:
    texts: list[str] = []
    started = time.time()
    try:
        with auto.UIAutomationInitializerInThread():
            root = auto.ControlFromHandle(window.hwnd)
            for control, _depth in auto.WalkControl(root, includeTop=True, maxDepth=30) if root else ():
                if time.time() - started > budget or sum(map(len, texts)) > limit:
                    break
                if control.ControlType in TEXT_KINDS:
                    text = _control_text(control, limit)
                elif control.ControlType == auto.ControlType.TextControl and len(control.Name or "") > 3:
                    text = control.Name.strip()
                else:
                    text = ""
                if text:
                    texts.append(text)
    except COMError as exc:
        log.info("Testo della finestra «%s» non leggibile: %s", window.title, exc)
    return "\n".join(dict.fromkeys(texts))[:limit]
