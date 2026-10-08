import logging
from typing import Optional, Dict, Any
from proxmoxer import ProxmoxAPI
from server.config.env import settings

logger = logging.getLogger("atena.proxmox_manager")

class ProxmoxManager:
    def __init__(self):
        self._proxmox: Optional[ProxmoxAPI] = None

    def _get_api(self) -> ProxmoxAPI:
        if self._proxmox is None:
            if not settings.PROXMOX_HOST:
                raise ValueError("PROXMOX_HOST is not configured in settings.")
            
            kwargs = {
                "host": settings.PROXMOX_HOST,
                "verify_ssl": settings.PROXMOX_VERIFY_SSL
            }
            if settings.PROXMOX_TOKEN_ID and settings.PROXMOX_TOKEN_SECRET:
                kwargs["user"] = settings.PROXMOX_USER
                kwargs["token_name"] = settings.PROXMOX_TOKEN_ID
                kwargs["token_value"] = settings.PROXMOX_TOKEN_SECRET
            elif settings.PROXMOX_USER and settings.PROXMOX_PASSWORD:
                kwargs["user"] = settings.PROXMOX_USER
                kwargs["password"] = settings.PROXMOX_PASSWORD
            else:
                raise ValueError("Either Proxmox password or Token credentials must be provided.")
                
            self._proxmox = ProxmoxAPI(**kwargs)
        return self._proxmox

    async def get_nodes(self) -> list:
        try:
            px = self._get_api()
            return px.nodes.get()
        except Exception as e:
            logger.error(f"Failed to get proxmox nodes: {e}")
            return [{"error": str(e)}]

    async def execute_api_call(self, method: str, path: str, data: Optional[Dict[str, Any]] = None) -> Any:
        try:
            px = self._get_api()
            
            if path.startswith("/"):
                path = path[1:]
                
            parts = path.split("/")
            endpoint = px
            for part in parts:
                if part:
                    endpoint = endpoint(part)
                    
            if method.upper() == "GET":
                return endpoint.get()
            elif method.upper() == "POST":
                return endpoint.post(**(data or {}))
            elif method.upper() == "PUT":
                return endpoint.put(**(data or {}))
            elif method.upper() == "DELETE":
                return endpoint.delete(**(data or {}))
            else:
                return {"error": f"Unsupported method: {method}"}
        except Exception as e:
            logger.error(f"Proxmox API call failed ({method} {path}): {e}")
            return {"error": str(e)}

proxmox_manager = ProxmoxManager()
