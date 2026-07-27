from __future__ import annotations

from typing import Any

from app.core.logger import JarvisLogger


class WSAuthenticator:
    """Authentication hook for WebSocket connections.

    Override :meth:`authenticate` to implement custom auth logic.
    The default implementation accepts all connections.
    """

    async def authenticate(
        self,
        client_id: str,
        token: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        """Authenticate a WebSocket client.

        Parameters
        ----------
        client_id:
            Unique client identifier.
        token:
            Optional authentication token from the query string.
        headers:
            Optional HTTP headers from the initial upgrade request.

        Returns
        -------
        A dict of client metadata on success, or ``None`` to reject.
        """
        return {"client_id": client_id}

    async def on_connect(self, client_id: str, metadata: dict[str, Any]) -> None:
        """Called after a client has been authenticated and registered."""
        JarvisLogger.info("WebSocket client connected: %s", client_id)

    async def on_disconnect(self, client_id: str) -> None:
        """Called after a client disconnects."""
        JarvisLogger.info("WebSocket client disconnected: %s", client_id)
