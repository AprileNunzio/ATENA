from typing import Dict, Any
from .base import RemoteProtocol
from server.features.remote_control.utils import ensure_dependency

class BaseUnixSSHProtocol(RemoteProtocol):
    def __init__(self, hostname: str, username: str, key_path: str):
        ensure_dependency("asyncssh", "asyncssh")
        self.hostname = hostname
        self.username = username
        self.key_path = key_path
        
    async def _run(self, cmd: str) -> str:
        import asyncssh
        async with asyncssh.connect(self.hostname, username=self.username, client_keys=[self.key_path]) as conn:
            result = await conn.run(cmd, check=True)
            return result.stdout

    async def _safe_exec(self, cmd: str) -> Dict[str, Any]:
        try:
            return {"status": "success", "data": await self._run(cmd)}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def reboot_system(self, force: bool = False) -> Dict[str, Any]:
        return await self._safe_exec("sudo shutdown -r +1")

    async def list_active_users(self) -> Dict[str, Any]:
        return await self._safe_exec("who")

    async def get_network_info(self) -> Dict[str, Any]:
        return await self._safe_exec("ifconfig | grep 'inet ' | grep -v 127.0.0.1 || ip -4 a")

    async def get_disk_space(self) -> Dict[str, Any]:
        return await self._safe_exec("df -h")
