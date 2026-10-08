from typing import Dict, Any
from .unix_base import BaseUnixSSHProtocol

class DebianSSHProtocol(BaseUnixSSHProtocol):
    async def check_updates(self) -> Dict[str, Any]:
        return await self._safe_exec("apt list --upgradable 2>/dev/null | grep -v 'Listing...'")

    async def get_system_status(self) -> Dict[str, Any]:
        return await self._safe_exec("uptime -p && free -h")

    async def restart_service(self, service_name: str) -> Dict[str, Any]:
        return await self._safe_exec(f"sudo systemctl restart '{service_name}'")

    async def get_cpu_usage(self) -> Dict[str, Any]:
        return await self._safe_exec("top -bn1 | grep 'Cpu(s)'")


class RhelSSHProtocol(BaseUnixSSHProtocol):
    async def check_updates(self) -> Dict[str, Any]:
        return await self._safe_exec("dnf check-update -q 2>/dev/null || yum check-update -q")

    async def get_system_status(self) -> Dict[str, Any]:
        return await self._safe_exec("uptime -p && free -h")

    async def restart_service(self, service_name: str) -> Dict[str, Any]:
        return await self._safe_exec(f"sudo systemctl restart '{service_name}'")

    async def get_cpu_usage(self) -> Dict[str, Any]:
        return await self._safe_exec("top -bn1 | grep 'Cpu(s)'")


class MacSSHProtocol(BaseUnixSSHProtocol):
    async def check_updates(self) -> Dict[str, Any]:
        return await self._safe_exec("softwareupdate -l")

    async def get_system_status(self) -> Dict[str, Any]:
        return await self._safe_exec("uptime && sysctl hw.memsize")

    async def restart_service(self, service_name: str) -> Dict[str, Any]:
        return await self._safe_exec(f"sudo launchctl stop {service_name} && sudo launchctl start {service_name}")

    async def get_cpu_usage(self) -> Dict[str, Any]:
        return await self._safe_exec("top -l 1 | grep 'CPU usage'")


class BsdSSHProtocol(BaseUnixSSHProtocol):
    async def check_updates(self) -> Dict[str, Any]:
        return await self._safe_exec("pkg audit -F && pkg version -vL =")

    async def get_system_status(self) -> Dict[str, Any]:
        return await self._safe_exec("uptime && sysctl hw.physmem")

    async def restart_service(self, service_name: str) -> Dict[str, Any]:
        return await self._safe_exec(f"sudo service '{service_name}' restart")

    async def get_cpu_usage(self) -> Dict[str, Any]:
        return await self._safe_exec("top -d 1 | grep CPU")

    async def get_disk_space(self) -> Dict[str, Any]:
        return await self._safe_exec("df -h -t ufs,zfs")
