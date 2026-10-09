import ipaddress
import os
import subprocess
import urllib.parse
import webbrowser
from pathlib import Path

WINDOW = "--window-size=720,430"
BROWSERS = (
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe",
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Microsoft/Edge/Application/msedge.exe",
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
)


def _private(host: str) -> bool:
    if host.endswith((".local", ".lan", ".home.arpa")):
        return True
    try:
        return ipaddress.ip_address(host).is_private
    except ValueError:
        return False


def trusted(url: str, server: str) -> bool:
    parts = urllib.parse.urlsplit(str(url or ""))
    server_host = urllib.parse.urlsplit(server if "//" in server else f"//{server}").hostname or ""
    host = (parts.hostname or "").lower()
    return (parts.scheme in ("http", "https") and parts.path == "/tv/watch" and bool(parts.query)
            and (host == server_host.lower() or _private(host)))


def open_window(url: str) -> str:
    browser = next((b for b in BROWSERS if b.is_file()), None)
    if browser:
        subprocess.Popen([str(browser), f"--app={url}", WINDOW], close_fds=True)
        return browser.stem
    webbrowser.open(url)
    return "browser"
