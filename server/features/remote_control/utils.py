import sys
import subprocess
import importlib

def ensure_dependency(module_name: str, package_name: str) -> None:
    try:
        importlib.import_module(module_name)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package_name, "--quiet"])
        importlib.invalidate_caches()
