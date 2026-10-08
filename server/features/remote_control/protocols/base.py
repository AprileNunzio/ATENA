import abc
from typing import Dict, Any

class RemoteProtocol(abc.ABC):
    @abc.abstractmethod
    async def check_updates(self) -> Dict[str, Any]:
        pass

    @abc.abstractmethod
    async def get_system_status(self) -> Dict[str, Any]:
        pass

    @abc.abstractmethod
    async def get_disk_space(self) -> Dict[str, Any]:
        pass

    @abc.abstractmethod
    async def restart_service(self, service_name: str) -> Dict[str, Any]:
        pass

    @abc.abstractmethod
    async def reboot_system(self, force: bool = False) -> Dict[str, Any]:
        pass

    @abc.abstractmethod
    async def get_cpu_usage(self) -> Dict[str, Any]:
        pass

    @abc.abstractmethod
    async def get_network_info(self) -> Dict[str, Any]:
        pass

    @abc.abstractmethod
    async def list_active_users(self) -> Dict[str, Any]:
        pass
