import asyncio
from typing import Dict, Any
from .base import RemoteProtocol
from server.features.remote_control.utils import ensure_dependency

class WinRMProtocol(RemoteProtocol):
    def __init__(self, hostname: str, username: str, password: str):
        ensure_dependency("winrm", "pywinrm")
        self.hostname = hostname
        self.username = username
        self.password = password
        
    async def _run(self, script: str) -> str:
        import winrm
        loop = asyncio.get_event_loop()
        def _exec():
            session = winrm.Session(self.hostname, auth=(self.username, self.password), transport='ntlm')
            res = session.run_ps(script)
            if res.status_code != 0:
                raise RuntimeError(res.std_err.decode())
            return res.std_out.decode()
        return await loop.run_in_executor(None, _exec)

    async def _safe_exec(self, script: str) -> Dict[str, Any]:
        try:
            return {"status": "success", "data": await self._run(script)}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def check_updates(self) -> Dict[str, Any]:
        return await self._safe_exec("Get-WindowsUpdate -AcceptAll -Install | ConvertTo-Json")

    async def get_system_status(self) -> Dict[str, Any]:
        return await self._safe_exec("Get-ComputerInfo | Select-Object WindowsProductName, WindowsVersion, CsTotalPhysicalMemory | ConvertTo-Json")

    async def get_disk_space(self) -> Dict[str, Any]:
        return await self._safe_exec("Get-Volume | Select-Object DriveLetter, FileSystemLabel, SizeRemaining, Size | ConvertTo-Json")

    async def restart_service(self, service_name: str) -> Dict[str, Any]:
        return await self._safe_exec(f"Restart-Service -Name '{service_name}' -Force -PassThru | ConvertTo-Json")

    async def reboot_system(self, force: bool = False) -> Dict[str, Any]:
        flag = "-Force" if force else ""
        return await self._safe_exec(f"Restart-Computer {flag}")

    async def get_cpu_usage(self) -> Dict[str, Any]:
        return await self._safe_exec("(Get-WmiObject Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average")

    async def get_network_info(self) -> Dict[str, Any]:
        return await self._safe_exec("Get-NetIPAddress -AddressFamily IPv4 | Select-Object IPAddress, InterfaceAlias | ConvertTo-Json")

    async def list_active_users(self) -> Dict[str, Any]:
        return await self._safe_exec("Get-WmiObject Win32_ComputerSystem | Select-Object UserName | ConvertTo-Json")
