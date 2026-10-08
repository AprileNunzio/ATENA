import sys
import subprocess
import importlib
import os

class SystemAutoInstaller:
    @staticmethod
    def require_python(package_name, module_name=None):
        module = module_name or package_name.replace("-", "_")
        try:
            importlib.import_module(module)
        except ImportError:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
            importlib.invalidate_caches()
            importlib.import_module(module)

    @staticmethod
    def require_node(package_name, project_dir):
        try:
            subprocess.check_call(["npm", "list", package_name], cwd=project_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            subprocess.check_call(["npm", "install", package_name], cwd=project_dir)
