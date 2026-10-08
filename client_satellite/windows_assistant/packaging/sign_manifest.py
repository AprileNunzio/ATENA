import base64
import hashlib
import json
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

REPOSITORY = "AprileNunzio/ATENA"
KEY_ENV = "ATENA_ASSISTANT_SIGNING_KEY"


def manifest(installer: Path, version: str) -> bytes:
    data = installer.read_bytes()
    url = f"https://github.com/{REPOSITORY}/releases/download/assistant-v{version}/{installer.name}"
    body = {"version": version, "url": url, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def main(installer: str, version: str, out_dir: str) -> int:
    secret = os.environ.get(KEY_ENV, "").strip()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    body = manifest(Path(installer), version)
    (out / "manifest.json").write_bytes(body)
    if not secret:
        print(f"{KEY_ENV} assente: manifesto NON firmato, i PC non installeranno questo aggiornamento da soli")
        return 0
    key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(secret))
    (out / "manifest.sig").write_bytes(base64.b64encode(key.sign(body)))
    print(f"Manifesto firmato per la versione {version}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:4]))
