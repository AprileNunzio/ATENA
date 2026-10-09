import asyncio

import httpx
from config import ollama_remote, ollama_url

from features.brain import scope
from features.brain.brains import CATALOG, brains, norm
from features.cloud import models as cloud_models
from features.cloud import servers
from features.cloud.catalog import PROVIDERS, make_ref
from features.cloud.client import CloudError
from features.cloud.vault import vault

_SIZES = {norm(m["name"]): m["size_gb"] for m in CATALOG}
_LABELS = {norm(m["name"]): m["label"] for m in CATALOG}
_CLOUD_TIMEOUT = 12


def _local_models(installed: list[str]) -> list[dict]:
    rows = [{"ref": n, "label": _LABELS.get(norm(n), n), "size_gb": _SIZES.get(norm(n)), "installed": True}
            for n in installed if "embed" not in n and "bge" not in n]
    have = {norm(n) for n in installed}
    rows += [{"ref": m["name"], "label": m["label"], "size_gb": m["size_gb"], "installed": False}
             for m in CATALOG if m["roles"] and norm(m["name"]) not in have]
    return rows


async def _cloud_models(pid: str) -> tuple[list[str], str]:
    try:
        data = await asyncio.wait_for(cloud_models.available(pid), _CLOUD_TIMEOUT)
    except (asyncio.TimeoutError, httpx.HTTPError, CloudError, ValueError) as exc:
        return [], f"elenco modelli non disponibile ({type(exc).__name__})"
    return data["models"][:80], data.get("error", "")


def default_cloud_model(pid: str) -> str:
    spec = next((p for p in PROVIDERS if p.id == pid), None)
    return vault.get(pid).get("model") or (spec.models[0] if spec and spec.models else "")


async def catalog() -> dict:
    installed = await brains.installed()
    configured = [p for p in PROVIDERS if vault.configured(p.id)]
    server_rows, cloud_lists = await asyncio.gather(
        servers.overview(), asyncio.gather(*(_cloud_models(p.id) for p in configured)))
    local = {"kind": scope.LOCAL, "id": "local",
             "name": ollama_url().split("//", 1)[-1] if ollama_remote() else "Questo server",
             "online": bool(installed), "models": _local_models(installed)}
    server_list = [{"kind": scope.SERVER, "id": row["id"], "name": row["name"], "online": row["online"],
                    "error": row["error"], "models": [{"ref": make_ref(row["id"], m), "label": m} for m in row["models"]]}
                   for row in server_rows]
    cloud = []
    for spec, (names, error) in zip(configured, cloud_lists):
        ref_kind = scope.origin(make_ref(spec.id, names[0] if names else default_cloud_model(spec.id) or "x"))
        cloud.append({"kind": ref_kind, "id": spec.id, "name": spec.name, "online": True, "error": error,
                      "default": default_cloud_model(spec.id),
                      "models": [{"ref": make_ref(spec.id, m), "label": m} for m in names]})
    available = [{"id": p.id, "name": p.name} for p in PROVIDERS if not vault.configured(p.id)]
    return {"local": local, "servers": server_list + [c for c in cloud if c["kind"] == scope.SERVER],
            "cloud": [c for c in cloud if c["kind"] == scope.CLOUD], "connectable": available}
