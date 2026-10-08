from typing import Dict, Any
from .base import RemoteProtocol
from server.features.remote_control.utils import ensure_dependency

class RestApiProtocol(RemoteProtocol):
    def __init__(self, base_url: str, api_key: str):
        ensure_dependency("aiohttp", "aiohttp")
        self.base_url = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {api_key}"}
        
    async def _req(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        import aiohttp
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.request(method, f"{self.base_url}{endpoint}", **kwargs) as resp:
                    resp.raise_for_status()
                    return {"status": "success", "data": await resp.json()}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def check_updates(self) -> Dict[str, Any]:
        return await self._req("POST", "/api/v1/updates/check")

    async def get_system_status(self) -> Dict[str, Any]:
        return await self._req("GET", "/api/v1/system/status")

    async def get_disk_space(self) -> Dict[str, Any]:
        return await self._req("GET", "/api/v1/system/disk")

    async def restart_service(self, service_name: str) -> Dict[str, Any]:
        return await self._req("POST", "/api/v1/services/restart", json={"service": service_name})

    async def reboot_system(self, force: bool = False) -> Dict[str, Any]:
        return await self._req("POST", "/api/v1/system/reboot", json={"force": force})

    async def get_cpu_usage(self) -> Dict[str, Any]:
        return await self._req("GET", "/api/v1/system/cpu")

    async def get_network_info(self) -> Dict[str, Any]:
        return await self._req("GET", "/api/v1/system/network")

    async def list_active_users(self) -> Dict[str, Any]:
        return await self._req("GET", "/api/v1/system/users")
