from __future__ import annotations

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.ws.admin import AdminManager
from app.ws.ai_stream import AIStreamManager
from app.ws.auth import WSAuthenticator
from app.ws.commands import CommandExecutionManager
from app.ws.file_transfer import FileTransferManager
from app.ws.manager import WebSocketConnectionManager
from app.ws.schemas import ServerMessage, WSMessageType

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

    authenticator: WSAuthenticator | None = getattr(
        websocket.app.state, "ws_authenticator", None,
    )
    ai_stream: AIStreamManager | None = getattr(
        websocket.app.state, "ai_stream_manager", None,
    )
    cmd_exec: CommandExecutionManager | None = getattr(
        websocket.app.state, "command_execution_manager", None,
    )
    ft_mgr: FileTransferManager | None = getattr(
        websocket.app.state, "file_transfer_manager", None,
    )
    admin: AdminManager | None = getattr(
        websocket.app.state, "admin_manager", None,
    )

    info = await manager.connect(websocket, client_id=client_id, token=token)
    if info is None:
        return

    cid = info.client_id

    try:
        while True:
            raw = await websocket.receive_text()

            if authenticator:
                if not await authenticator.check_rate_limit(cid):
                    if await manager.is_connected(cid):
                        await manager.send(
                            cid,
                            ServerMessage(
                                type=WSMessageType.ERROR,
                                payload={"error": "rate limit exceeded"},
                            ),
                        )
                    continue
                if await authenticator.try_handle_auth_message(cid, manager, raw):
                    continue

            if ai_stream and await ai_stream.try_handle_message(cid, raw):
                continue
            if cmd_exec and await cmd_exec.try_handle_message(cid, raw):
                continue
            if ft_mgr and await ft_mgr.try_handle_message(cid, raw):
                continue
            if admin and await admin.try_handle_message(cid, raw):
                continue
            response = await manager.handle_message(cid, raw)
            if response is not None:
                await manager.send(cid, response)
    except WebSocketDisconnect:
        pass
    finally:
        if authenticator:
            await authenticator.on_disconnect(cid)
        if ai_stream:
            await ai_stream.cleanup(cid)
        if cmd_exec:
            await cmd_exec.cleanup(cid)
        if ft_mgr:
            await ft_mgr.cleanup(cid)
        await manager.disconnect(cid)
