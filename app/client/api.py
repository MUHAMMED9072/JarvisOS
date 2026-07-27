from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.client.models import (
    DiagnosticsReport,
    HealthCheck,
    MetricsSnapshot,
    PluginInfo,
    ServerInfo,
    SkillInfo,
    SystemStatus,
)


class RestClient:
    """Async REST client for the JARVIS API.

    Supports configurable URL, timeout, retries, and authentication.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        timeout: float = 30.0,
        retry_count: int = 3,
        api_key: str | None = None,
        bearer_token: str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._retry_count = retry_count
        self._api_key = api_key
        self._bearer_token = bearer_token
        self._client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if self._client is not None:
            return
        headers: dict[str, str] = {}
        if self._api_key:
            headers["Authorization"] = f"apikey {self._api_key}"
        elif self._bearer_token:
            headers["Authorization"] = f"Bearer {self._bearer_token}"
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
            headers=headers,
        )

    async def stop(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def is_started(self) -> bool:
        return self._client is not None

    # ------------------------------------------------------------------
    # Core request method
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError("RestClient not started. Call start() first.")

        last_error: Exception | None = None
        for attempt in range(max(1, self._retry_count + 1)):
            try:
                resp = await self._client.request(method, path, **kwargs)
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as exc:
                if attempt < self._retry_count and exc.response.status_code >= 500:
                    last_error = exc
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                raise
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt < self._retry_count:
                    last_error = exc
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                raise

        raise last_error  # type: ignore[misc]

    # ------------------------------------------------------------------
    # Typed HTTP methods
    # ------------------------------------------------------------------

    async def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._request("GET", path, params=params)

    async def post(self, path: str, json: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._request("POST", path, json=json)

    async def put(self, path: str, json: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._request("PUT", path, json=json)

    async def delete(self, path: str) -> dict[str, Any]:
        return await self._request("DELETE", path)

    async def patch(self, path: str, json: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._request("PATCH", path, json=json)

    # ------------------------------------------------------------------
    # High-level API methods
    # ------------------------------------------------------------------

    async def health(self) -> dict[str, Any]:
        return await self.get("/api/v1/health")

    async def status(self) -> dict[str, Any]:
        return await self.get("/api/v1/status")

    async def config(self) -> dict[str, Any]:
        return await self.get("/api/v1/config")

    async def services(self) -> dict[str, Any]:
        return await self.get("/api/v1/services")

    async def get_ws_metrics(self) -> dict[str, Any]:
        return await self.get("/api/v1/ws/metrics")

    async def get_ws_health(self) -> dict[str, Any]:
        return await self.get("/api/v1/ws/health")

    async def get_ws_diagnostics(self) -> dict[str, Any]:
        return await self.get("/api/v1/ws/diagnostics")

    async def list_plugins(self) -> list[dict[str, Any]]:
        data = await self.get("/api/v1/plugins")
        return data.get("plugins", [])

    async def get_plugin(self, name: str) -> dict[str, Any]:
        return await self.get(f"/api/v1/plugins/{name}")

    async def list_skills(self) -> list[dict[str, Any]]:
        data = await self.get("/api/v1/skills")
        return data.get("skills", [])

    async def ai_chat(self, message: str, model: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"message": message}
        if model:
            body["model"] = model
        return await self.post("/api/v1/ai/chat", json=body)

    async def ai_stream(self, message: str, model: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"message": message}
        if model:
            body["model"] = model
        return await self.post("/api/v1/ai/chat/stream", json=body)
