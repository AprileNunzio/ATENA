import hashlib
import hmac
import json
import logging
import os
import tempfile
import threading
from typing import Any, Callable, Dict, List, Optional

from server.features.skill_synthesis.domain.tool import TOOL_NAME, DynamicTool, ToolError

logger = logging.getLogger("atena.skill_synthesis.store")

KeyProvider = Callable[[], str]
SIGNATURE_FIELD = "signature"
_CONTEXT = b"atena.dynamic_tools.v1"


def _canonical(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _derive(secret: str) -> bytes:
    return hmac.new(secret.encode("utf-8"), _CONTEXT, hashlib.sha256).digest()


class JsonToolStore:
    def __init__(self, directory: str, key_provider: Optional[KeyProvider] = None) -> None:
        self._dir = directory
        self._key_provider = key_provider
        self._lock = threading.Lock()
        os.makedirs(self._dir, mode=0o700, exist_ok=True)

    @property
    def signed(self) -> bool:
        return self._key_provider is not None

    def all(self) -> List[DynamicTool]:
        tools: List[DynamicTool] = []
        with self._lock:
            for entry in sorted(os.scandir(self._dir), key=lambda e: e.name):
                if not entry.name.endswith(".json") or not entry.is_file(follow_symlinks=False):
                    continue
                tool = self._read(entry.path)
                if tool is not None:
                    tools.append(tool)
        return tools

    def get(self, name: str) -> Optional[DynamicTool]:
        if not TOOL_NAME.match(name):
            return None
        with self._lock:
            return self._read(os.path.join(self._dir, f"{name}.json"))

    def save(self, tool: DynamicTool) -> None:
        tool.validate()
        payload = tool.to_dict()
        if self._key_provider is not None:
            payload[SIGNATURE_FIELD] = self._sign(payload)
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        with self._lock:
            handle, temporary = tempfile.mkstemp(dir=self._dir, suffix=".tmp")
            try:
                with os.fdopen(handle, "w", encoding="utf-8") as stream:
                    stream.write(text)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.chmod(temporary, 0o600)
                os.replace(temporary, os.path.join(self._dir, f"{tool.name}.json"))
            except BaseException:
                if os.path.exists(temporary):
                    os.unlink(temporary)
                raise

    def delete(self, name: str) -> bool:
        if not TOOL_NAME.match(name):
            return False
        with self._lock:
            try:
                os.unlink(os.path.join(self._dir, f"{name}.json"))
            except FileNotFoundError:
                return False
        return True

    def _sign(self, payload: Dict[str, Any]) -> str:
        body = {k: v for k, v in payload.items() if k != SIGNATURE_FIELD}
        return hmac.new(_derive(self._key_provider()), _canonical(body), hashlib.sha256).hexdigest()

    def _authentic(self, payload: Dict[str, Any]) -> bool:
        if self._key_provider is None:
            return True
        signature = payload.get(SIGNATURE_FIELD)
        return isinstance(signature, str) and hmac.compare_digest(self._sign(payload), signature)

    def _read(self, path: str) -> Optional[DynamicTool]:
        try:
            with open(path, encoding="utf-8") as stream:
                payload = json.load(stream)
            if not isinstance(payload, dict):
                raise ToolError("not an object")
            if not self._authentic(payload):
                logger.warning("refusing tool file %s: missing or invalid signature", os.path.basename(path))
                return None
            tool = DynamicTool.from_dict(payload)
            if os.path.basename(path) != f"{tool.name}.json":
                logger.warning("refusing tool file %s: name does not match its content", os.path.basename(path))
                return None
            return tool
        except FileNotFoundError:
            return None
        except (OSError, ValueError, ToolError):
            logger.warning("ignoring unreadable tool file %s", os.path.basename(path))
            return None
