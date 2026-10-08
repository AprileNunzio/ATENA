import socket
import time
import psutil
from server.core.agent_registry.pool_manager import agent_pool
from server.features.presence_privacy.models import SystemTelemetryData

_START_TIME = time.time()

class SystemMetricsCollector:
    @staticmethod
    def get_local_ip() -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    @classmethod
    def collect(cls) -> SystemTelemetryData:
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        ip = cls.get_local_ip()
        conns = len(psutil.net_connections()) if hasattr(psutil, "net_connections") else 1
        uptime = time.time() - _START_TIME

        base_watts = 25.0
        dynamic_watts = (cpu / 100.0) * 45.0
        watts = round(base_watts + dynamic_watts, 1)

        energy_mode = "ECO" if cpu < 30 else ("DYNAMIC" if cpu < 70 else "BOOST")
        agents = agent_pool.list_agents()

        return SystemTelemetryData(
            cpu_percent=round(cpu, 1),
            memory_percent=round(mem.percent, 1),
            memory_used_mb=round(mem.used / (1024 * 1024), 1),
            memory_total_mb=round(mem.total / (1024 * 1024), 1),
            disk_percent=round(disk.percent, 1),
            local_ip=ip,
            active_connections=conns,
            estimated_power_watts=watts,
            energy_mode=energy_mode,
            uptime_seconds=round(uptime, 1),
            active_agents=agents,
        )

system_metrics_collector = SystemMetricsCollector()
