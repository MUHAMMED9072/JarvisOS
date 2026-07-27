from __future__ import annotations

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.ws.manager import WebSocketConnectionManager

router = APIRouter(tags=["WebSocket"])


@router.websocket("/api/v1/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str | None = Query(None, description="Optional auth token"),
    client_id: str | None = Query(None, description="Optional client identifier"),
):
    manager: WebSocketConnectionManager | None = getattr(
        websocket.app.state, "ws_manager", None,
    )
    if manager is None:
        await websocket.close(code=1011, reason="WebSocket manager not available")
        return

    info = await manager.connect(websocket, client_id=client_id, token=token)
    if info is None:
        return

    cid = info.client_id

    try:
        while True:
            raw = await websocket.receive_text()
            response = await manager.handle_message(cid, raw)
            if response is not None:
                await manager.send(cid, response)
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(cid)
