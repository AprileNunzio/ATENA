import os
import json
from typing import Dict, Any

from server.config.env import settings
from .protocols.base import RemoteProtocol
from .protocols.winrm_protocol import WinRMProtocol
from .protocols.windows_ssh_protocol import WindowsSSHProtocol
from .protocols.linux_protocols import DebianSSHProtocol, RhelSSHProtocol, MacSSHProtocol, BsdSSHProtocol
from .protocols.rest_protocol import RestApiProtocol


class RemoteComputerManager:
    def __init__(self, config_path: str = None):
        self._computers: Dict[str, RemoteProtocol] = {}
        self.config_path = config_path or os.path.join(settings.DATA_DIR, "network_map.json")
        self.load_from_config()
        
    def load_from_config(self) -> None:
        if not os.path.exists(self.config_path):
            return
            
        with open(self.config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        for pc_name, conf in data.get("computers", {}).items():
            ptype = conf.get("protocol")
            ip = conf.get("ip")
            user = conf.get("username")
            pw = conf.get("password")
            key = conf.get("key_path")
            url = conf.get("url")
            api_key = conf.get("api_key")
            
            if ptype == "winrm":
                self.add_computer(pc_name, WinRMProtocol(ip, user, pw))
            elif ptype == "ssh":
                self.add_computer(pc_name, WindowsSSHProtocol(ip, user, key))
            elif ptype == "linux_ssh":
                self.add_computer(pc_name, DebianSSHProtocol(ip, user, key))
            elif ptype == "rhel_ssh":
                self.add_computer(pc_name, RhelSSHProtocol(ip, user, key))
            elif ptype == "mac_ssh":
                self.add_computer(pc_name, MacSSHProtocol(ip, user, key))
            elif ptype == "bsd_ssh":
                self.add_computer(pc_name, BsdSSHProtocol(ip, user, key))
            elif ptype == "rest":
                self.add_computer(pc_name, RestApiProtocol(url, api_key))

    def add_computer(self, name: str, protocol: RemoteProtocol) -> None:
        self._computers[name.upper()] = protocol

    async def dispatch_command(self, name: str, command: str, **kwargs) -> Dict[str, Any]:
        name = name.upper()
        
        if name not in self._computers:
            return {"status": "error", "message": f"PC {name} non trovato nella rete di ATENA."}
        
        protocol = self._computers[name]
        
        cmd_map = {
            "status": protocol.get_system_status,
            "updates": protocol.check_updates,
            "disk": protocol.get_disk_space,
            "reboot": lambda: protocol.reboot_system(kwargs.get("force", False)),
            "cpu": protocol.get_cpu_usage,
            "network": protocol.get_network_info,
            "users": protocol.list_active_users
        }
        
        if command == "restart_service":
            return await protocol.restart_service(kwargs.get("service_name", ""))
            
        if command in cmd_map:
            return await cmd_map[command]()
            
        return {"status": "error", "message": f"Comando {command} non supportato"}
