from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO

from app.core.logger import JarvisLogger
from app.ws.manager import WebSocketConnectionManager
from app.ws.schemas import ServerMessage, WSMessageType


class FileTransferManager:
    """Manage secure file transfers over WebSocket connections.

    Supports chunked upload and download with SHA-256 verification,
    resume, progress reporting, cancellation, and configurable limits.
    """

    def __init__(
        self,
        ws_manager: WebSocketConnectionManager,
        upload_dir: str | Path = "",
        download_dir: str | Path = "",
        max_file_size: int = 104857600,
        chunk_size: int = 65536,
    ) -> None:
        self._ws = ws_manager
        self._upload_dir = Path(upload_dir) if upload_dir else Path.cwd() / "uploads"
        self._download_dir = (
            Path(download_dir) if download_dir else Path.cwd() / "downloads"
        )
        self._max_file_size = max_file_size
        self._chunk_size = chunk_size
        self._transfers: dict[str, _TransferState] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_active_count(self, client_id: str | None = None) -> int:
        """Number of active (in-progress) transfers."""
        async with self._lock:
            if client_id is None:
                return len(self._transfers)
            return sum(
                1 for t in self._transfers.values() if t.client_id == client_id
            )

    async def cleanup(self, client_id: str) -> None:
        """Cancel all transfers for a disconnected client."""
        count = await self._cancel_all(client_id)
        if count:
            JarvisLogger.info(
                "Cleaned up %d transfer(s) for disconnected client %s",
                count,
                client_id,
            )

    async def cancel_all(self, client_id: str) -> int:
        """Cancel every transfer owned by *client_id*. Returns the count."""
        return await self._cancel_all(client_id)

    async def _cancel_all(self, client_id: str) -> int:
        count = 0
        async with self._lock:
            for tid, state in list(self._transfers.items()):
                if state.client_id == client_id:
                    await self._abort_transfer(state)
                    del self._transfers[tid]
                    count += 1
        return count

    # ------------------------------------------------------------------
    # Incoming message routing
    # ------------------------------------------------------------------

    async def try_handle_message(
        self,
        client_id: str,
        raw: str,
    ) -> bool:
        """Parse *raw* as a file transfer control message.

        Returns ``True`` if the message was recognised and handled.
        """
        try:
            data = json.loads(raw)
            msg_type = data.get("type")
        except json.JSONDecodeError:
            return False

        payload: dict = data.get("payload") or {}

        if msg_type == "file.upload.start":
            await self._handle_upload_start(client_id, payload)
            return True
        if msg_type == "file.upload.chunk":
            await self._handle_upload_chunk(client_id, payload)
            return True
        if msg_type == "file.upload.complete":
            await self._handle_upload_complete(client_id, payload)
            return True
        if msg_type == "file.upload.cancel":
            await self._handle_upload_cancel(client_id, payload)
            return True
        if msg_type == "file.download.start":
            await self._handle_download_start(client_id, payload)
            return True
        if msg_type == "file.download.cancel":
            await self._handle_download_cancel(client_id, payload)
            return True

        return False

    # ------------------------------------------------------------------
    # Upload handlers
    # ------------------------------------------------------------------

    async def _handle_upload_start(
        self,
        client_id: str,
        payload: dict[str, Any],
    ) -> None:
        filename: str = payload.get("filename", "")
        file_size: int = payload.get("file_size", 0)
        expected_sha256: str = payload.get("sha256", "")
        resume: bool = payload.get("resume", False)
        resume_id: str | None = payload.get("resume_id")

        if not filename:
            await self._send_error(client_id, "", "filename is required")
            return

        safe_name = Path(filename).name
        if not safe_name:
            await self._send_error(client_id, "", "invalid filename")
            return

        if file_size > self._max_file_size:
            await self._send_error(
                client_id, "",
                f"file size {file_size} exceeds maximum {self._max_file_size}",
            )
            return

        self._upload_dir.mkdir(parents=True, exist_ok=True)

        transfer_id = f"ft-{uuid.uuid4().hex[:12]}"

        if resume and resume_id:
            async with self._lock:
                old = self._transfers.get(resume_id)
                if old and old.client_id == client_id and old.status == "interrupted":
                    transfer_id = resume_id
                    filepath = old.filepath
                    bytes_received = old.bytes_transferred
                    await self._close_transfer(old)
                    state = _TransferState(
                        transfer_id=transfer_id,
                        client_id=client_id,
                        direction="upload",
                        filename=safe_name,
                        filepath=filepath,
                        file_size=file_size,
                        bytes_transferred=bytes_received,
                        sha256=expected_sha256,
                        status="transferring",
                    )
                    self._transfers[transfer_id] = state
                    if await self._ws.is_connected(client_id):
                        await self._ws.send(
                            client_id,
                            ServerMessage(
                                type=WSMessageType.FILE_UPLOAD_STARTED,
                                payload={
                                    "transfer_id": transfer_id,
                                    "filename": safe_name,
                                    "file_size": file_size,
                                    "bytes_received": bytes_received,
                                    "chunk_size": self._chunk_size,
                                    "resumed": True,
                                },
                            ),
                        )
                    return

        filepath = self._upload_dir / f"{transfer_id}_{safe_name}"

        state = _TransferState(
            transfer_id=transfer_id,
            client_id=client_id,
            direction="upload",
            filename=safe_name,
            filepath=filepath,
            file_size=file_size,
            sha256=expected_sha256,
            status="transferring",
            started_at=time.time(),
        )

        async with self._lock:
            self._transfers[transfer_id] = state

        if await self._ws.is_connected(client_id):
            await self._ws.send(
                client_id,
                ServerMessage(
                    type=WSMessageType.FILE_UPLOAD_STARTED,
                    payload={
                        "transfer_id": transfer_id,
                        "filename": safe_name,
                        "file_size": file_size,
                        "bytes_received": 0,
                        "chunk_size": self._chunk_size,
                        "resumed": False,
                    },
                ),
            )

    async def _handle_upload_chunk(
        self,
        client_id: str,
        payload: dict[str, Any],
    ) -> None:
        transfer_id: str = payload.get("transfer_id", "")
        data_b64: str = payload.get("data", "")
        byte_offset: int = payload.get("byte_offset", 0)

        if not transfer_id or not data_b64:
            return

        state = self._transfers.get(transfer_id)
        if state is None or state.client_id != client_id:
            return

        if state.status != "transferring":
            return

        chunk_bytes = _decode_b64(data_b64)
        actual_offset = state.bytes_transferred

        if byte_offset != actual_offset:
            await self._send_error(
                client_id, transfer_id,
                f"offset mismatch: expected {actual_offset}, got {byte_offset}",
            )
            return

        try:
            if state.file is None:
                state.file = open(state.filepath, "ab")

            state.file.write(chunk_bytes)
            state.file.flush()
            state.bytes_transferred += len(chunk_bytes)
            state.chunks_received += 1

            await self._send_progress(
                client_id, transfer_id, "upload",
                state.bytes_transferred, state.file_size,
            )
        except OSError as exc:
            await self._abort_transfer(state)
            async with self._lock:
                self._transfers.pop(transfer_id, None)
            await self._send_error(client_id, transfer_id, str(exc))

    async def _handle_upload_complete(
        self,
        client_id: str,
        payload: dict[str, Any],
    ) -> None:
        transfer_id: str = payload.get("transfer_id", "")

        state = self._transfers.get(transfer_id)
        if state is None or state.client_id != client_id:
            return

        await self._close_file(state)

        if state.file_size > 0 and state.bytes_transferred != state.file_size:
            await self._send_error(
                client_id, transfer_id,
                f"bytes mismatch: received {state.bytes_transferred}, expected {state.file_size}",
            )

        if state.sha256:
            actual_hash = await self._compute_hash(state.filepath)
            if actual_hash != state.sha256:
                await self._send_error(
                    client_id, transfer_id,
                    f"SHA-256 mismatch: expected {state.sha256}, got {actual_hash}",
                )
                state.status = "failed"
                async with self._lock:
                    self._transfers.pop(transfer_id, None)
                return

        state.status = "completed"
        async with self._lock:
            self._transfers.pop(transfer_id, None)

        if await self._ws.is_connected(client_id):
            hash_val = await self._compute_hash(state.filepath)
            await self._ws.send(
                client_id,
                ServerMessage(
                    type=WSMessageType.FILE_UPLOAD_DONE,
                    payload={
                        "transfer_id": transfer_id,
                        "filename": state.filename,
                        "file_size": state.file_size,
                        "bytes_transferred": state.bytes_transferred,
                        "sha256": hash_val,
                        "chunks_received": state.chunks_received,
                    },
                ),
            )

    async def _handle_upload_cancel(
        self,
        client_id: str,
        payload: dict[str, Any],
    ) -> None:
        transfer_id: str = payload.get("transfer_id", "")

        async with self._lock:
            state = self._transfers.get(transfer_id)
            if state is None or state.client_id != client_id:
                return
            await self._abort_transfer(state)
            del self._transfers[transfer_id]

        if await self._ws.is_connected(client_id):
            await self._ws.send(
                client_id,
                ServerMessage(
                    type=WSMessageType.FILE_ERROR,
                    payload={
                        "transfer_id": transfer_id,
                        "error": "cancelled",
                    },
                ),
            )

    # ------------------------------------------------------------------
    # Download handlers
    # ------------------------------------------------------------------

    async def _handle_download_start(
        self,
        client_id: str,
        payload: dict[str, Any],
    ) -> None:
        filename: str = payload.get("filename", "")
        byte_offset: int = payload.get("byte_offset", 0)
        transfer_id: str = payload.get("transfer_id") or f"ft-{uuid.uuid4().hex[:12]}"

        if not filename:
            await self._send_error(client_id, transfer_id, "filename is required")
            return

        safe_name = Path(filename).name
        if not safe_name:
            await self._send_error(client_id, transfer_id, "invalid filename")
            return

        filepath = self._download_dir / safe_name
        if not filepath.exists():
            await self._send_error(
                client_id, transfer_id,
                f"file not found: {safe_name}",
            )
            return

        file_size = filepath.stat().st_size

        state = _TransferState(
            transfer_id=transfer_id,
            client_id=client_id,
            direction="download",
            filename=safe_name,
            filepath=filepath,
            file_size=file_size,
            bytes_transferred=byte_offset,
            status="transferring",
            started_at=time.time(),
        )

        task = asyncio.create_task(
            self._run_download(state, client_id, byte_offset),
        )
        state.task = task

        async with self._lock:
            self._transfers[transfer_id] = state

        if await self._ws.is_connected(client_id):
            await self._ws.send(
                client_id,
                ServerMessage(
                    type=WSMessageType.FILE_DOWNLOAD_INIT,
                    payload={
                        "transfer_id": transfer_id,
                        "filename": safe_name,
                        "file_size": file_size,
                        "chunk_size": self._chunk_size,
                        "bytes_sent": byte_offset,
                    },
                ),
            )

    async def _handle_download_cancel(
        self,
        client_id: str,
        payload: dict[str, Any],
    ) -> None:
        transfer_id: str = payload.get("transfer_id", "")

        async with self._lock:
            state = self._transfers.get(transfer_id)
            if state is None or state.client_id != client_id:
                return
            if state.task:
                state.task.cancel()
            await self._close_file(state)
            del self._transfers[transfer_id]

    async def _run_download(
        self,
        state: _TransferState,
        client_id: str,
        byte_offset: int,
    ) -> None:
        try:
            await asyncio.sleep(0)
            file_size = state.file_size
            chunk_size = self._chunk_size

            async def send_chunk(
                data_b64: str,
                offset: int,
                is_last: bool,
            ) -> bool:
                if not await self._ws.is_connected(client_id):
                    return False
                sent = await self._ws.send(
                    client_id,
                    ServerMessage(
                        type=WSMessageType.FILE_DOWNLOAD_CHUNK,
                        payload={
                            "transfer_id": state.transfer_id,
                            "data": data_b64,
                            "byte_offset": offset,
                            "bytes_length": len(_decode_b64(data_b64)),
                            "is_last": is_last,
                        },
                    ),
                )
                if not sent:
                    return False
                state.bytes_transferred = offset + len(_decode_b64(data_b64))
                return True

            with open(state.filepath, "rb") as f:
                if byte_offset > 0:
                    f.seek(byte_offset)

                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    chunk_b64 = _encode_b64(chunk)
                    offset = state.bytes_transferred
                    is_last = (f.tell() >= file_size)
                    ok = await send_chunk(chunk_b64, offset, is_last)
                    if not ok:
                        return
                    await self._send_progress(
                        client_id, state.transfer_id, "download",
                        state.bytes_transferred, file_size,
                    )

            state.status = "completed"
            async with self._lock:
                self._transfers.pop(state.transfer_id, None)

            if await self._ws.is_connected(client_id):
                hash_val = await self._compute_hash(state.filepath)
                await self._ws.send(
                    client_id,
                    ServerMessage(
                        type=WSMessageType.FILE_DOWNLOAD_DONE,
                        payload={
                            "transfer_id": state.transfer_id,
                            "filename": state.filename,
                            "file_size": file_size,
                            "bytes_transferred": state.bytes_transferred,
                            "sha256": hash_val,
                        },
                    ),
                )

        except asyncio.CancelledError:
            pass
        except Exception as exc:
            JarvisLogger.exception("Download %s failed: %s", state.transfer_id, exc)
            state.status = "failed"
            async with self._lock:
                self._transfers.pop(state.transfer_id, None)
            if await self._ws.is_connected(client_id):
                await self._ws.send(
                    client_id,
                    ServerMessage(
                        type=WSMessageType.FILE_ERROR,
                        payload={
                            "transfer_id": state.transfer_id,
                            "error": str(exc),
                        },
                    ),
                )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _compute_hash(self, filepath: Path) -> str:
        """Compute SHA-256 hash of a file."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _hash_file, filepath)

    async def _close_file(self, state: _TransferState) -> None:
        if state.file is not None:
            try:
                state.file.close()
            except Exception:
                pass
            state.file = None

    async def _close_transfer(self, state: _TransferState) -> None:
        """Close file handle and cancel task without deleting the file."""
        if state.task:
            state.task.cancel()
        await self._close_file(state)

    async def _abort_transfer(self, state: _TransferState) -> None:
        """Cancel transfer and remove partial file."""
        await self._close_transfer(state)
        if state.filepath.exists():
            try:
                state.filepath.unlink(missing_ok=True)
            except Exception:
                pass

    async def _send_progress(
        self,
        client_id: str,
        transfer_id: str,
        direction: str,
        bytes_transferred: int,
        file_size: int,
    ) -> None:
        if not await self._ws.is_connected(client_id):
            return
        pct = round(bytes_transferred / file_size * 100, 1) if file_size > 0 else 0
        await self._ws.send(
            client_id,
            ServerMessage(
                type=WSMessageType.FILE_PROGRESS,
                payload={
                    "transfer_id": transfer_id,
                    "direction": direction,
                    "bytes_transferred": bytes_transferred,
                    "file_size": file_size,
                    "progress_pct": pct,
                },
            ),
        )

    async def _send_error(
        self,
        client_id: str,
        transfer_id: str,
        error: str,
    ) -> None:
        if not await self._ws.is_connected(client_id):
            return
        await self._ws.send(
            client_id,
            ServerMessage(
                type=WSMessageType.FILE_ERROR,
                payload={
                    "transfer_id": transfer_id,
                    "error": error,
                },
            ),
        )


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


@dataclass
class _TransferState:
    transfer_id: str = ""
    client_id: str = ""
    direction: str = ""
    filename: str = ""
    filepath: Path = field(default_factory=Path)
    file_size: int = 0
    bytes_transferred: int = 0
    sha256: str = ""
    status: str = "initiating"
    chunk_size: int = 65536
    started_at: float = 0.0
    task: asyncio.Task | None = None
    file: BinaryIO | None = None
    chunks_received: int = 0


def _encode_b64(data: bytes) -> str:
    """Encode bytes to base64 string."""
    import base64
    return base64.b64encode(data).decode("ascii")


def _decode_b64(data: str) -> bytes:
    """Decode base64 string to bytes."""
    import base64
    return base64.b64decode(data)


def _hash_file(filepath: Path) -> str:
    """Compute SHA-256 of a file (runs in thread pool)."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()
