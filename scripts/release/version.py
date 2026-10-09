import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION_FILE = ROOT / "VERSION"
SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
V = r"\d+\.\d+(?:\.\d+)?"


@dataclass(frozen=True)
class Target:
    path: str
    pattern: str
    count: int = 1


TARGETS = (
    Target("installer_wizard/backend/config.py", rf'(?m)^(VERSION = "){V}(")'),
    Target("server/cmd/main.py", rf'(version="){V}(")'),
    Target("server/cmd/main.py", rf'("version": "){V}(")'),
    Target("server/core/context_graph/graph_client.py", rf'("version": "){V}(", "status")'),
    Target("installer_wizard/features/capabilities/mcp.py", rf'(INFO = \{{"name": "atena-os", "version": "){V}(")'),
    Target("installer_wizard/features/mcpclient/client.py", rf'("clientInfo": \{{"name": "atena-os", "version": "){V}(")'),
    Target("client_web/package.json", rf'(?m)^(  "version": "){V}(")'),
    Target("client_web/package-lock.json", rf'(?m)^(  "version": "){V}(")'),
    Target("client_web/package-lock.json", rf'(?s)(  "packages": \{{\s+"": \{{\s+"name": "[^"]+",\s+"version": "){V}(")'),
    Target("native/Cargo.toml", rf'(?m)^(version = "){V}(")'),
    Target("native/Cargo.lock", rf'(name = "atena-bus-core"\r?\nversion = "){V}(")'),
    Target("native/Cargo.lock", rf'(name = "atena-egress"\r?\nversion = "){V}(")'),
    Target("native/Cargo.lock", rf'(name = "atena-native"\r?\nversion = "){V}(")'),
    Target("native/Cargo.lock", rf'(name = "atena-netguard"\r?\nversion = "){V}(")'),
    Target("native/Cargo.lock", rf'(name = "atena-langid"\r?\nversion = "){V}(")'),
    Target("native/crates/atena-native/pyproject.toml", rf'(?m)^(version = "){V}(")'),
    Target("client_apk/app/build.gradle.kts", rf'(versionName = "){V}(")'),
    Target("client_satellite/context_bridge/setup_msi.py", rf'(version="){V}(")'),
    Target("client_satellite/linux_edge/satellite.py", rf'(?m)^(VERSION = "){V}(")'),
    Target("client_satellite/linux_edge/rpa_daemon.py", rf'(?m)^(VERSION = "){V}(")'),
    Target("client_satellite/windows_assistant/settings/paths.py", rf'(?m)^(VERSION = "){V}(")'),
)
VERSION_CODE = Target("client_apk/app/build.gradle.kts", r"(versionCode = )\d+()")


def read_version() -> str:
    value = VERSION_FILE.read_text(encoding="utf-8").strip()
    if not SEMVER.match(value):
        raise ValueError(f"VERSION non valida: {value!r}")
    return value


def bumped(version: str, part: str) -> str:
    major, minor, patch = (int(x) for x in SEMVER.match(version).groups())
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def version_code(version: str) -> int:
    major, minor, patch = (int(x) for x in SEMVER.match(version).groups())
    return major * 1_000_000 + minor * 1_000 + patch


def _rewrite(text: str, target: Target, value: str) -> str:
    updated, found = re.subn(target.pattern, lambda m: f"{m.group(1)}{value}{m.group(2)}", text)
    if found != target.count:
        raise LookupError(f"{target.path}: attese {target.count} occorrenze di versione, trovate {found}")
    return updated


def apply(version: str) -> list[str]:
    changed: dict[str, str] = {}
    for target in (*TARGETS, VERSION_CODE):
        path = ROOT / target.path
        text = changed.get(target.path) or path.read_bytes().decode("utf-8")
        value = str(version_code(version)) if target is VERSION_CODE else version
        changed[target.path] = _rewrite(text, target, value)
    for relative, text in changed.items():
        (ROOT / relative).write_bytes(text.encode("utf-8"))
    VERSION_FILE.write_text(version + "\n", encoding="utf-8")
    return sorted(changed)


def mismatches(version: str) -> list[str]:
    wrong = []
    for target in TARGETS:
        text = (ROOT / target.path).read_bytes().decode("utf-8")
        found = [m.group(0) for m in re.finditer(target.pattern, text)]
        if len(found) != target.count or any(version not in f for f in found):
            wrong.append(f"{target.path}: {found}")
    gradle = (ROOT / VERSION_CODE.path).read_text(encoding="utf-8")
    if f"versionCode = {version_code(version)}" not in gradle:
        wrong.append(f"{VERSION_CODE.path}: versionCode diverso da {version_code(version)}")
    return wrong


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="version")
    sub = parser.add_subparsers(dest="command", required=True)
    bump = sub.add_parser("bump")
    bump.add_argument("part", choices=("patch", "minor", "major"), nargs="?", default="patch")
    setter = sub.add_parser("set")
    setter.add_argument("value")
    sub.add_parser("check")
    args = parser.parse_args(argv)
    if args.command == "check":
        wrong = mismatches(read_version())
        print("\n".join(wrong) or f"versione {read_version()} allineata")
        return 1 if wrong else 0
    target = bumped(read_version(), args.part) if args.command == "bump" else args.value
    if not SEMVER.match(target):
        print(f"versione non valida: {target}")
        return 2
    apply(target)
    print(target)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
