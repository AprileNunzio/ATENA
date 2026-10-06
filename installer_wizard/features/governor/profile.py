CLASSES = ("low", "mid", "high")
JOB_KINDS = ("realtime", "interactive", "background", "maintenance")
SLOTS = {
    "low": {"realtime": 2, "interactive": 1, "background": 1, "maintenance": 1},
    "mid": {"realtime": 3, "interactive": 2, "background": 2, "maintenance": 1},
    "high": {"realtime": 4, "interactive": 4, "background": 4, "maintenance": 2},
}
WIDGETS = {"low": {"active": 2, "ambient": 1}, "mid": {"active": 4, "ambient": 2}, "high": {"active": 8, "ambient": 3}}
QUALITY = {"low": "reduced", "mid": "full", "high": "full"}
TIERS = ("full", "reduced", "minimal")


def classify(cores: int, ram_gb: float, avx2: bool) -> str:
    if cores <= 2 or ram_gb < 3 or (cores <= 4 and not avx2):
        return "low"
    if cores >= 8 and ram_gb >= 12 and avx2:
        return "high"
    return "mid"


def has_avx2() -> bool:
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as f:
            return "avx2" in f.read()
    except OSError:
        return True
