import os
import sys
import subprocess
import requests
import zipfile
import shutil
from pathlib import Path

def apply_update(download_url: str) -> None:
    current_dir = Path(__file__).parent.absolute()
    temp_zip = current_dir / "update.zip"
    extract_dir = current_dir / "update_temp"

    response = requests.get(download_url, stream=True)
    response.raise_for_status()
    with open(temp_zip, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir()

    with zipfile.ZipFile(temp_zip, 'r') as zip_ref:
        zip_ref.extractall(extract_dir)

    temp_zip.unlink()

    script_name = "updater.bat" if os.name == "nt" else "updater.sh"
    script_path = current_dir / script_name

    if os.name == "nt":
        script_content = f"""@echo off
timeout /t 3 /nobreak > NUL
xcopy /s /y "{extract_dir}\\*" "{current_dir}"
rmdir /s /q "{extract_dir}"
start "" "{sys.executable}" "{current_dir}\\main.py"
del "%~f0"
"""
    else:
        script_content = f"""#!/bin/bash
sleep 3
cp -R "{extract_dir}"/* "{current_dir}"/
rm -rf "{extract_dir}"
nohup "{sys.executable}" "{current_dir}/main.py" > /dev/null 2>&1 &
rm -- "$0"
"""

    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script_content)

    if os.name != "nt":
        os.chmod(script_path, 0o755)

    if os.name == "nt":
        subprocess.Popen([str(script_path)], creationflags=subprocess.CREATE_NEW_CONSOLE)
    else:
        subprocess.Popen([str(script_path)], start_new_session=True)
    
    sys.exit(0)
