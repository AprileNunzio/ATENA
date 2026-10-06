import os
import platform
import subprocess
import shutil
try:
    import psutil
except ImportError:
    psutil = None
from typing import Optional
from pydantic import BaseModel

class HardwareProfile(BaseModel):
    ram_total_gb: float
    ram_available_gb: float
    cpu_cores: int
    cpu_arch: str
    has_cuda: bool
    has_metal: bool
    has_vulkan: bool
    gpu_name: Optional[str] = None
    vram_total_gb: float = 0.0
    vram_free_gb: float = 0.0
    tier: str
    recommended_system1: str
    recommended_system2: str
    system2_quantization: str
    supports_local: bool
    recommended_provider: str

class HardwareDetector:
    @staticmethod
    def _detect_cuda() -> tuple[bool, Optional[str], float, float]:
        if shutil.which("nvidia-smi") is not None:
            try:
                res = subprocess.run(
                    ["nvidia-smi", "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader,nounits"],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=5,
                )
                line = res.stdout.strip().split("\n")[0]
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 3:
                    gpu_name = parts[0]
                    vram_total = round(float(parts[1]) / 1024.0, 2)
                    vram_free = round(float(parts[2]) / 1024.0, 2)
                    return True, gpu_name, vram_total, vram_free
            except Exception:
                pass
        try:
            import torch
            if torch.cuda.is_available():
                name = torch.cuda.get_device_name(0)
                total = round(torch.cuda.get_device_properties(0).total_memory / (1024**3), 2)
                return True, name, total, total
        except Exception:
            pass
        return False, None, 0.0, 0.0

    @staticmethod
    def _detect_metal() -> tuple[bool, Optional[str], float]:
        if platform.system() == "Darwin" and platform.machine() == "arm64":
            try:
                res = subprocess.run(
                    ["sysctl", "-n", "machdep.cpu.brand_string"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                )
                chip = res.stdout.strip() or "Apple Silicon"
                mem = round(psutil.virtual_memory().total / (1024**3), 2) if psutil else 16.0
                return True, chip, mem
            except Exception:
                mem = round(psutil.virtual_memory().total / (1024**3), 2) if psutil else 16.0
                return True, "Apple Silicon", mem
        return False, None, 0.0

    @staticmethod
    def _detect_vulkan() -> bool:
        if shutil.which("vulkaninfo") is not None:
            return True
        vulkan_paths = [
            "/usr/lib/x86_64-linux-gnu/libvulkan.so.1",
            "/usr/lib/libvulkan.so.1",
            "C:\\Windows\\System32\\vulkan-1.dll",
        ]
        return any(os.path.exists(p) for p in vulkan_paths)

    @classmethod
    def detect(cls) -> HardwareProfile:
        if psutil:
            vmem = psutil.virtual_memory()
            ram_total = round(vmem.total / (1024**3), 2)
            ram_avail = round(vmem.available / (1024**3), 2)
            cores = psutil.cpu_count(logical=True) or (os.cpu_count() or 4)
        else:
            ram_total = 8.0
            ram_avail = 4.0
            cores = os.cpu_count() or 4
        arch = platform.machine().lower()

        cuda_ok, cuda_name, cuda_total, cuda_free = cls._detect_cuda()
        metal_ok, metal_name, metal_vram = cls._detect_metal()
        vulkan_ok = cls._detect_vulkan()

        gpu_name = cuda_name if cuda_ok else (metal_name if metal_ok else None)
        vram_total = cuda_total if cuda_ok else (metal_vram if metal_ok else 0.0)
        vram_free = cuda_free if cuda_ok else (metal_vram if metal_ok else 0.0)

        if cuda_ok and vram_total >= 14.0:
            tier = "high"
            sys1 = "qwen2.5:0.5b"
            sys2 = "qwen2.5:14b-instruct-q8_0"
            quant = "Q8"
            local = True
            provider = "ollama"
        elif metal_ok and ram_total >= 30.0:
            tier = "high"
            sys1 = "qwen2.5:0.5b"
            sys2 = "qwen2.5:14b-instruct-q8_0"
            quant = "Q8"
            local = True
            provider = "ollama"
        elif (cuda_ok and vram_total >= 6.0) or (metal_ok and ram_total >= 14.0) or ram_total >= 22.0:
            tier = "mid"
            sys1 = "qwen2.5:0.5b"
            sys2 = "qwen2.5:7b-instruct-q4_K_M"
            quant = "Q4"
            local = True
            provider = "ollama"
        elif (cuda_ok and vram_total >= 3.5) or ram_total >= 10.0:
            tier = "low"
            sys1 = "qwen2.5:0.5b"
            sys2 = "granite3.3:2b"
            quant = "Q4"
            local = True
            provider = "ollama"
        else:
            tier = "cpu"
            sys1 = "qwen2.5:0.5b"
            sys2 = "qwen2.5:1.5b-instruct-q4_K_M"
            quant = "Q4"
            local = False
            provider = "gemini"

        return HardwareProfile(
            ram_total_gb=ram_total,
            ram_available_gb=ram_avail,
            cpu_cores=cores,
            cpu_arch=arch,
            has_cuda=cuda_ok,
            has_metal=metal_ok,
            has_vulkan=vulkan_ok,
            gpu_name=gpu_name,
            vram_total_gb=vram_total,
            vram_free_gb=vram_free,
            tier=tier,
            recommended_system1=sys1,
            recommended_system2=sys2,
            system2_quantization=quant,
            supports_local=local,
            recommended_provider=provider,
        )

hardware_detector = HardwareDetector()
