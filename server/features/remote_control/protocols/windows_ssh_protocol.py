from typing import Dict, Any
from .base import RemoteProtocol
from server.features.remote_control.utils import ensure_dependency

class WindowsSSHProtocol(RemoteProtocol):
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

    async def check_updates(self) -> Dict[str, Any]:
        return await self._safe_exec('powershell -Command "Get-WindowsUpdate -Install -AcceptAll"')

    async def get_system_status(self) -> Dict[str, Any]:
        return await self._safe_exec("systeminfo")

    async def get_disk_space(self) -> Dict[str, Any]:
        return await self._safe_exec('powershell -Command "Get-Volume"')

    async def restart_service(self, service_name: str) -> Dict[str, Any]:
        return await self._safe_exec(f'powershell -Command "Restart-Service \'{service_name}\' -Force"')

    async def reboot_system(self, force: bool = False) -> Dict[str, Any]:
        flag = "/f" if force else ""
        return await self._safe_exec(f"shutdown /r /t 5 {flag}")

    async def get_cpu_usage(self) -> Dict[str, Any]:
        return await self._safe_exec('wmic cpu get loadpercentage')

    async def get_network_info(self) -> Dict[str, Any]:
        return await self._safe_exec("ipconfig")

    async def list_active_users(self) -> Dict[str, Any]:
        return await self._safe_exec("quser")
