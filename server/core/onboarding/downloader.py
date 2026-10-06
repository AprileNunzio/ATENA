import asyncio
import json
import httpx
from typing import AsyncGenerator, Callable, Optional
from pydantic import BaseModel
from server.config.env import settings

class DownloadProgress(BaseModel):
    model_name: str
    status: str
    total_bytes: int = 0
    completed_bytes: int = 0
    percentage: float = 0.0
    is_finished: bool = False
    error: Optional[str] = None

class ModelDownloader:
    def __init__(self, ollama_url: str = settings.OLLAMA_BASE_URL) -> None:
        self.ollama_url = ollama_url

    async def is_model_installed(self, model_name: str) -> bool:
        normalized = model_name if ":" in model_name else f"{model_name}:latest"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(f"{self.ollama_url}/api/tags")
                if res.status_code == 200:
                    models = res.json().get("models", [])
                    return any(m.get("name") == normalized or m.get("model") == normalized for m in models)
        except Exception:
            return False
        return False

    async def stream_pull(self, model_name: str) -> AsyncGenerator[DownloadProgress, None]:
        payload = {"model": model_name, "stream": True}
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("POST", f"{self.ollama_url}/api/pull", json=payload) as response:
                    if response.status_code != 200:
                        yield DownloadProgress(
                            model_name=model_name,
                            status="error",
                            error=f"HTTP {response.status_code}",
                            is_finished=True,
                        )
                        return
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if "error" in data:
                            yield DownloadProgress(
                                model_name=model_name,
                                status="failed",
                                error=data["error"],
                                is_finished=True,
                            )
                            return
                        status = data.get("status", "")
                        total = data.get("total", 0)
                        completed = data.get("completed", 0)
                        pct = round((completed / total * 100.0), 2) if total > 0 else 0.0
                        finished = status == "success"
                        yield DownloadProgress(
                            model_name=model_name,
                            status=status,
                            total_bytes=total,
                            completed_bytes=completed,
                            percentage=pct,
                            is_finished=finished,
                        )
                        if finished:
                            break
        except Exception as exc:
            yield DownloadProgress(
                model_name=model_name,
                status="failed",
                error=str(exc),
                is_finished=True,
            )

    async def pull_model(
        self, model_name: str, progress_hook: Optional[Callable[[DownloadProgress], None]] = None
    ) -> bool:
        success = False
        async for item in self.stream_pull(model_name):
            if progress_hook:
                if asyncio.iscoroutinefunction(progress_hook):
                    await progress_hook(item)
                else:
                    progress_hook(item)
            if item.status == "success" or (item.is_finished and not item.error):
                success = True
        return success

model_downloader = ModelDownloader()
