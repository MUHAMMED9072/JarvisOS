"""Tests for Remote File Transfer over WebSockets (P12-06)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ws.file_transfer import FileTransferManager
from app.ws.manager import WebSocketConnectionManager
from app.ws.schemas import ServerMessage, WSMessageType


# ==========================================================================
# Helpers
# ==========================================================================


def _make_msg(msg_type: str, **payload: Any) -> str:
    return json.dumps({"type": msg_type, "payload": payload})


def _make_b64(data: bytes) -> str:
    import base64
    return base64.b64encode(data).decode("ascii")


def _chunks(data: bytes, size: int) -> list[bytes]:
    return [data[i:i + size] for i in range(0, len(data), size)]


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _get_sent_payload(ws_mock: AsyncMock, index: int = 0) -> dict:
    call_args = ws_mock.send.call_args_list[index]
    msg: ServerMessage = call_args[0][1]
    return msg.payload


def _get_sent_type(ws_mock: AsyncMock, index: int = 0) -> str:
    call_args = ws_mock.send.call_args_list[index]
    msg: ServerMessage = call_args[0][1]
    return msg.type.value


async def _make_env(**kwargs: Any) -> tuple[FileTransferManager, AsyncMock, Path]:
    """Create a test environment with temp directories."""
    tmpdir = Path(tempfile.mkdtemp())
    upload_dir = tmpdir / "uploads"
    download_dir = tmpdir / "downloads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    download_dir.mkdir(parents=True, exist_ok=True)

    ws_mock = AsyncMock(spec=WebSocketConnectionManager)
    ws_mock.is_connected = AsyncMock(return_value=True)
    ws_mock.send = AsyncMock(return_value=True)

    mgr = FileTransferManager(
        ws_manager=ws_mock,
        upload_dir=str(upload_dir),
        download_dir=str(download_dir),
        **kwargs,
    )
    return mgr, ws_mock, tmpdir


def _seed_download_file(download_dir: Path, filename: str, content: bytes) -> Path:
    """Create a file in the download directory for download tests."""
    filepath = download_dir / filename
    filepath.write_bytes(content)
    return filepath


# ==========================================================================
# Upload Tests
# ==========================================================================


class TestUpload:
    """File upload over WebSocket."""

    @pytest.mark.asyncio
    async def test_upload_start_sends_started(self) -> None:
        """file.upload.start responds with file.upload.started."""
        mgr, ws, _ = await _make_env()
        cid = "client-1"

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("file.upload.start", filename="test.txt", file_size=100),
        )
        assert handled is True
        await asyncio.sleep(0.05)

        assert ws.send.called
        msg_type = _get_sent_type(ws, 0)
        assert msg_type == WSMessageType.FILE_UPLOAD_STARTED.value
        payload = _get_sent_payload(ws, 0)
        assert payload.get("filename") == "test.txt"
        assert payload.get("file_size") == 100
        assert payload.get("transfer_id", "").startswith("ft-")
        assert payload.get("bytes_received") == 0

    @pytest.mark.asyncio
    async def test_upload_single_chunk(self) -> None:
        """Upload a file in a single chunk."""
        mgr, ws, tmpdir = await _make_env()
        cid = "client-1"
        content = b"Hello, JARVIS file transfer!"
        expected_hash = _hash_bytes(content)

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("file.upload.start", filename="hello.txt", file_size=len(content)),
        )
        assert handled is True
        await asyncio.sleep(0.05)

        payload = _get_sent_payload(ws, 0)
        tid = payload["transfer_id"]

        handled = await mgr.try_handle_message(
            cid,
            _make_msg(
                "file.upload.chunk",
                transfer_id=tid,
                data=_make_b64(content),
                byte_offset=0,
            ),
        )
        assert handled is True
        await asyncio.sleep(0.05)

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("file.upload.complete", transfer_id=tid),
        )
        assert handled is True
        await asyncio.sleep(0.05)

        last_payload = _get_sent_payload(ws, -1)
        assert last_payload.get("transfer_id") == tid
        assert last_payload.get("sha256") == expected_hash

        saved = Path(last_payload["filename"]) if last_payload.get("filename") else None
        for f in tmpdir.rglob("*"):
            if f.is_file() and f.name.endswith("hello.txt"):
                assert f.read_bytes() == content
                break

    @pytest.mark.asyncio
    async def test_upload_multiple_chunks(self) -> None:
        """Upload a file split across multiple chunks."""
        mgr, ws, _ = await _make_env(chunk_size=32)
        cid = "client-1"
        content = b"A" * 200
        expected_hash = _hash_bytes(content)

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("file.upload.start", filename="multi_chunk.bin", file_size=len(content), sha256=expected_hash),
        )
        assert handled is True
        await asyncio.sleep(0.05)

        tid = _get_sent_payload(ws, 0)["transfer_id"]
        ws.send.reset_mock()

        for i, chunk in enumerate(_chunks(content, 32)):
            handled = await mgr.try_handle_message(
                cid,
                _make_msg(
                    "file.upload.chunk",
                    transfer_id=tid,
                    data=_make_b64(chunk),
                    byte_offset=i * 32,
                ),
            )
            assert handled is True
            await asyncio.sleep(0.02)

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("file.upload.complete", transfer_id=tid),
        )
        assert handled is True
        await asyncio.sleep(0.05)

        last_payload = _get_sent_payload(ws, -1)
        assert last_payload.get("sha256") == expected_hash
        assert last_payload.get("bytes_transferred") == 200

    @pytest.mark.asyncio
    async def test_upload_with_sha256_verification(self) -> None:
        """SHA-256 hash is verified on upload complete."""
        mgr, ws, _ = await _make_env()
        cid = "client-1"
        content = b"verify-me"
        correct_hash = _hash_bytes(content)

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("file.upload.start", filename="verify.txt", file_size=len(content), sha256=correct_hash),
        )
        assert handled is True
        await asyncio.sleep(0.05)

        tid = _get_sent_payload(ws, 0)["transfer_id"]

        handled = await mgr.try_handle_message(
            cid,
            _make_msg(
                "file.upload.chunk",
                transfer_id=tid,
                data=_make_b64(content),
                byte_offset=0,
            ),
        )
        assert handled is True
        await asyncio.sleep(0.05)

        ws.send.reset_mock()

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("file.upload.complete", transfer_id=tid),
        )
        assert handled is True
        await asyncio.sleep(0.05)

        last_type = _get_sent_type(ws, -1)
        assert last_type == WSMessageType.FILE_UPLOAD_DONE.value

    @pytest.mark.asyncio
    async def test_upload_sha256_mismatch_reports_error(self) -> None:
        """SHA-256 mismatch returns file.error."""
        mgr, ws, _ = await _make_env()
        cid = "client-1"
        content = b"actual-content"
        wrong_hash = "0" * 64

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("file.upload.start", filename="bad_hash.txt", file_size=len(content), sha256=wrong_hash),
        )
        assert handled is True
        await asyncio.sleep(0.05)

        tid = _get_sent_payload(ws, 0)["transfer_id"]

        handled = await mgr.try_handle_message(
            cid,
            _make_msg(
                "file.upload.chunk",
                transfer_id=tid,
                data=_make_b64(content),
                byte_offset=0,
            ),
        )
        assert handled is True
        await asyncio.sleep(0.05)

        ws.send.reset_mock()

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("file.upload.complete", transfer_id=tid),
        )
        assert handled is True
        await asyncio.sleep(0.05)

        last_type = _get_sent_type(ws, -1)
        assert last_type == WSMessageType.FILE_ERROR.value

    @pytest.mark.asyncio
    async def test_upload_size_limit_exceeded(self) -> None:
        """file.upload.start with oversized file returns error."""
        mgr, ws, _ = await _make_env(max_file_size=50)
        cid = "client-1"

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("file.upload.start", filename="big.txt", file_size=100),
        )
        assert handled is True
        await asyncio.sleep(0.05)

        last_type = _get_sent_type(ws, -1)
        assert last_type == WSMessageType.FILE_ERROR.value
        assert "exceeds maximum" in _get_sent_payload(ws, -1).get("error", "")

    @pytest.mark.asyncio
    async def test_upload_missing_filename(self) -> None:
        """file.upload.start without filename returns error."""
        mgr, ws, _ = await _make_env()
        cid = "client-1"

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("file.upload.start", file_size=100),
        )
        assert handled is True
        await asyncio.sleep(0.05)

        last_type = _get_sent_type(ws, -1)
        assert last_type == WSMessageType.FILE_ERROR.value
        assert "filename is required" in _get_sent_payload(ws, -1).get("error", "")

    @pytest.mark.asyncio
    async def test_upload_cancel(self) -> None:
        """file.upload.cancel stops an active upload."""
        mgr, ws, _ = await _make_env()
        cid = "client-1"

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("file.upload.start", filename="cancel_test.txt", file_size=1000),
        )
        assert handled is True
        await asyncio.sleep(0.05)

        tid = _get_sent_payload(ws, 0)["transfer_id"]

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("file.upload.cancel", transfer_id=tid),
        )
        assert handled is True
        await asyncio.sleep(0.05)

        assert await mgr.get_active_count(cid) == 0

    @pytest.mark.asyncio
    async def test_upload_cancel_nonexistent(self) -> None:
        """Cancelling a non-existent transfer is a no-op."""
        mgr, ws, _ = await _make_env()
        cid = "client-1"

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("file.upload.cancel", transfer_id="no-such-transfer"),
        )
        assert handled is True
        await asyncio.sleep(0.05)
        assert ws.send.call_count == 0


class TestUploadResume:
    """Resume interrupted uploads."""

    @pytest.mark.asyncio
    async def test_upload_resume_after_interruption(self) -> None:
        """Resume an interrupted upload from where it left off."""
        mgr, ws, _ = await _make_env(chunk_size=50)
        cid = "client-1"
        content = b"X" * 200
        expected_hash = _hash_bytes(content)

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("file.upload.start", filename="resume_test.bin", file_size=len(content)),
        )
        assert handled is True
        await asyncio.sleep(0.05)

        tid = _get_sent_payload(ws, 0)["transfer_id"]
        ws.send.reset_mock()

        first_chunks = _chunks(content[:100], 50)
        for i, chunk in enumerate(first_chunks):
            handled = await mgr.try_handle_message(
                cid,
                _make_msg(
                    "file.upload.chunk",
                    transfer_id=tid,
                    data=_make_b64(chunk),
                    byte_offset=i * 50,
                ),
            )
            assert handled is True
            await asyncio.sleep(0.02)

        state = mgr._transfers.get(tid)
        assert state is not None

        # Simulate interruption: close file handle, cancel task, keep file
        if state.file is not None:
            state.file.close()
            state.file = None
        if state.task:
            state.task.cancel()
        state.status = "interrupted"
        ws.send.reset_mock()

        handled = await mgr.try_handle_message(
            cid,
            _make_msg(
                "file.upload.start",
                filename="resume_test.bin",
                file_size=len(content),
                resume=True,
                resume_id=tid,
                sha256=expected_hash,
            ),
        )
        assert handled is True
        await asyncio.sleep(0.05)

        payload = _get_sent_payload(ws, 0)
        assert payload.get("resumed") is True
        assert payload.get("transfer_id") == tid

        remaining = content[100:]
        handled = await mgr.try_handle_message(
            cid,
            _make_msg(
                "file.upload.chunk",
                transfer_id=tid,
                data=_make_b64(remaining),
                byte_offset=100,
            ),
        )
        assert handled is True
        await asyncio.sleep(0.05)

        ws.send.reset_mock()

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("file.upload.complete", transfer_id=tid),
        )
        assert handled is True
        await asyncio.sleep(0.05)

        last_type = _get_sent_type(ws, -1)
        assert last_type == WSMessageType.FILE_UPLOAD_DONE.value

    @pytest.mark.asyncio
    async def test_offset_mismatch_reports_error(self) -> None:
        """Sending a chunk with wrong byte_offset returns error."""
        mgr, ws, _ = await _make_env()
        cid = "client-1"
        content = b"test data"

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("file.upload.start", filename="offset.txt", file_size=len(content)),
        )
        assert handled is True
        await asyncio.sleep(0.05)

        tid = _get_sent_payload(ws, 0)["transfer_id"]

        ws.send.reset_mock()

        handled = await mgr.try_handle_message(
            cid,
            _make_msg(
                "file.upload.chunk",
                transfer_id=tid,
                data=_make_b64(content),
                byte_offset=999,
            ),
        )
        assert handled is True
        await asyncio.sleep(0.05)

        last_type = _get_sent_type(ws, -1)
        assert last_type == WSMessageType.FILE_ERROR.value
        assert "offset mismatch" in _get_sent_payload(ws, -1).get("error", "")


class TestUploadProgress:
    """Progress reporting during uploads."""

    @pytest.mark.asyncio
    async def test_progress_sent_for_chunks(self) -> None:
        """Progress messages are sent during multi-chunk upload."""
        mgr, ws, _ = await _make_env(chunk_size=32)
        cid = "client-1"
        content = b"B" * 128

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("file.upload.start", filename="prog_test.bin", file_size=len(content)),
        )
        assert handled is True
        await asyncio.sleep(0.05)

        tid = _get_sent_payload(ws, 0)["transfer_id"]
        ws.send.reset_mock()

        for i, chunk in enumerate(_chunks(content, 32)):
            handled = await mgr.try_handle_message(
                cid,
                _make_msg(
                    "file.upload.chunk",
                    transfer_id=tid,
                    data=_make_b64(chunk),
                    byte_offset=i * 32,
                ),
            )
            assert handled is True
            await asyncio.sleep(0.02)

        progress_types = [
            _get_sent_type(ws, i)
            for i in range(ws.send.call_count)
        ]
        assert WSMessageType.FILE_PROGRESS.value in progress_types


# ==========================================================================
# Download Tests
# ==========================================================================


class TestDownload:
    """File download over WebSocket."""

    @pytest.mark.asyncio
    async def test_download_start_sends_init(self) -> None:
        """file.download.start responds with file.download.init."""
        mgr, ws, tmpdir = await _make_env()
        cid = "client-1"
        _seed_download_file(tmpdir / "downloads", "download_me.txt", b"file content")

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("file.download.start", filename="download_me.txt"),
        )
        assert handled is True
        await asyncio.sleep(0.05)

        payload = _get_sent_payload(ws, 0)
        assert payload.get("filename") == "download_me.txt"
        assert payload.get("file_size") == 12

    @pytest.mark.asyncio
    async def test_download_full_file(self) -> None:
        """Download an entire file."""
        mgr, ws, tmpdir = await _make_env(chunk_size=32)
        cid = "client-1"
        content = b"DOWNLOAD TEST CONTENT " * 10
        _seed_download_file(tmpdir / "downloads", "full_dl.bin", content)
        expected_hash = _hash_bytes(content)

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("file.download.start", filename="full_dl.bin"),
        )
        assert handled is True
        await asyncio.sleep(0.5)

        # Should receive: init + chunks + progress + done
        sent_types = [_get_sent_type(ws, i) for i in range(ws.send.call_count)]
        assert WSMessageType.FILE_DOWNLOAD_INIT.value in sent_types
        assert WSMessageType.FILE_DOWNLOAD_CHUNK.value in sent_types
        assert WSMessageType.FILE_DOWNLOAD_DONE.value in sent_types

        last_payload = _get_sent_payload(ws, -1)
        assert last_payload.get("sha256") == expected_hash
        assert last_payload.get("bytes_transferred") == len(content)

    @pytest.mark.asyncio
    async def test_download_with_byte_offset_resume(self) -> None:
        """Download resumes from a byte offset."""
        mgr, ws, tmpdir = await _make_env(chunk_size=64)
        cid = "client-1"
        content = b"RESUME TEST " * 20
        _seed_download_file(tmpdir / "downloads", "resume_dl.bin", content)

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("file.download.start", filename="resume_dl.bin", byte_offset=100),
        )
        assert handled is True
        await asyncio.sleep(0.3)

        last_payload = _get_sent_payload(ws, -1)
        assert last_payload.get("bytes_transferred") == len(content)
        assert last_payload.get("file_size") == len(content)

    @pytest.mark.asyncio
    async def test_download_file_not_found(self) -> None:
        """Download of non-existent file returns error."""
        mgr, ws, _ = await _make_env()
        cid = "client-1"

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("file.download.start", filename="no_such_file.txt"),
        )
        assert handled is True
        await asyncio.sleep(0.05)

        last_type = _get_sent_type(ws, -1)
        assert last_type == WSMessageType.FILE_ERROR.value
        assert "file not found" in _get_sent_payload(ws, -1).get("error", "")

    @pytest.mark.asyncio
    async def test_download_missing_filename(self) -> None:
        """file.download.start without filename returns error."""
        mgr, ws, _ = await _make_env()
        cid = "client-1"

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("file.download.start"),
        )
        assert handled is True
        await asyncio.sleep(0.05)

        last_type = _get_sent_type(ws, -1)
        assert last_type == WSMessageType.FILE_ERROR.value

    @pytest.mark.asyncio
    async def test_download_cancel(self) -> None:
        """file.download.cancel stops an active download."""
        mgr, ws, tmpdir = await _make_env()
        cid = "client-1"
        _seed_download_file(tmpdir / "downloads", "cancel_dl.bin", b"X" * 100000)

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("file.download.start", filename="cancel_dl.bin"),
        )
        assert handled is True
        assert await mgr.get_active_count(cid) > 0

        # Find the transfer_id
        payload = _get_sent_payload(ws, 0)
        tid = payload["transfer_id"]
        ws.send.reset_mock()

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("file.download.cancel", transfer_id=tid),
        )
        assert handled is True
        await asyncio.sleep(0.2)

        assert await mgr.get_active_count(cid) == 0


class TestDownloadProgress:
    """Progress reporting during downloads."""

    @pytest.mark.asyncio
    async def test_progress_sent_during_download(self) -> None:
        """Progress messages sent during download."""
        mgr, ws, tmpdir = await _make_env(chunk_size=64)
        cid = "client-1"
        content = b"C" * 300
        _seed_download_file(tmpdir / "downloads", "dl_prog.bin", content)

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("file.download.start", filename="dl_prog.bin"),
        )
        assert handled is True
        await asyncio.sleep(0.5)

        sent_types = [_get_sent_type(ws, i) for i in range(ws.send.call_count)]
        assert WSMessageType.FILE_PROGRESS.value in sent_types


# ==========================================================================
# Concurrent Transfers
# ==========================================================================


class TestConcurrent:
    """Concurrent file transfers."""

    @pytest.mark.asyncio
    async def test_concurrent_uploads(self) -> None:
        """Multiple uploads from the same client."""
        mgr, ws, _ = await _make_env()
        cid = "client-1"

        handled1 = await mgr.try_handle_message(
            cid,
            _make_msg("file.upload.start", filename="con1.txt", file_size=10),
        )
        handled2 = await mgr.try_handle_message(
            cid,
            _make_msg("file.upload.start", filename="con2.txt", file_size=20),
        )
        assert handled1 and handled2
        await asyncio.sleep(0.05)

        count = await mgr.get_active_count(cid)
        assert count == 2

    @pytest.mark.asyncio
    async def test_concurrent_upload_and_download(self) -> None:
        """Upload and download run concurrently."""
        mgr, ws, tmpdir = await _make_env()
        cid = "client-1"
        # Large file so download doesn't finish before we check
        _seed_download_file(tmpdir / "downloads", "concurrent_dl.txt", b"T" * 200000)

        handled1 = await mgr.try_handle_message(
            cid,
            _make_msg("file.upload.start", filename="up.txt", file_size=10),
        )
        handled2 = await mgr.try_handle_message(
            cid,
            _make_msg("file.download.start", filename="concurrent_dl.txt"),
        )
        assert handled1 and handled2
        await asyncio.sleep(0)

        count = await mgr.get_active_count(cid)
        assert count >= 1  # at least upload is still active

    @pytest.mark.asyncio
    async def test_multiple_clients_independent(self) -> None:
        """Transfers for different clients are independent."""
        mgr, ws, _ = await _make_env()
        cid1 = "client-1"
        cid2 = "client-2"

        await mgr.try_handle_message(
            cid1,
            _make_msg("file.upload.start", filename="c1.txt", file_size=10),
        )
        await mgr.try_handle_message(
            cid2,
            _make_msg("file.upload.start", filename="c2.txt", file_size=20),
        )
        await asyncio.sleep(0.05)

        assert await mgr.get_active_count(cid1) == 1
        assert await mgr.get_active_count(cid2) == 1


# ==========================================================================
# Disconnect and Cleanup
# ==========================================================================


class TestCleanup:
    """Disconnect and cleanup behavior."""

    @pytest.mark.asyncio
    async def test_cleanup_cancels_active_uploads(self) -> None:
        """Cleanup cancels active uploads."""
        mgr, ws, _ = await _make_env()
        cid = "client-1"

        await mgr.try_handle_message(
            cid,
            _make_msg("file.upload.start", filename="cleanup.txt", file_size=1000),
        )
        await asyncio.sleep(0.05)

        assert await mgr.get_active_count(cid) == 1

        await mgr.cleanup(cid)
        assert await mgr.get_active_count(cid) == 0

    @pytest.mark.asyncio
    async def test_cleanup_cancels_active_downloads(self) -> None:
        """Cleanup cancels active downloads."""
        mgr, ws, tmpdir = await _make_env()
        cid = "client-1"
        # Large file so download hasn't finished when we check
        _seed_download_file(tmpdir / "downloads", "cleanup_dl.txt", b"X" * 200000)

        await mgr.try_handle_message(
            cid,
            _make_msg("file.download.start", filename="cleanup_dl.txt"),
        )
        await asyncio.sleep(0)

        count = await mgr.get_active_count(cid)
        if count == 0:
            return  # download finished too fast, nothing to clean up

        await mgr.cleanup(cid)
        await asyncio.sleep(0.2)
        assert await mgr.get_active_count(cid) == 0

    @pytest.mark.asyncio
    async def test_cleanup_isolated_per_client(self) -> None:
        """Cleanup only affects the specified client."""
        mgr, ws, _ = await _make_env()
        cid1 = "client-1"
        cid2 = "client-2"

        await mgr.try_handle_message(
            cid1,
            _make_msg("file.upload.start", filename="a.txt", file_size=10),
        )
        await mgr.try_handle_message(
            cid2,
            _make_msg("file.upload.start", filename="b.txt", file_size=20),
        )
        await asyncio.sleep(0.05)

        await mgr.cleanup(cid1)
        assert await mgr.get_active_count(cid1) == 0
        assert await mgr.get_active_count(cid2) == 1

    @pytest.mark.asyncio
    async def test_disconnect_during_upload(self) -> None:
        """Disconnect during upload is handled gracefully."""
        ws_mock = AsyncMock(spec=WebSocketConnectionManager)
        ws_mock.is_connected = AsyncMock(return_value=True)
        ws_mock.send = AsyncMock(return_value=True)

        mgr = FileTransferManager(
            ws_manager=ws_mock,
            upload_dir=tempfile.mkdtemp(),
        )
        cid = "client-1"

        await mgr.try_handle_message(
            cid,
            _make_msg("file.upload.start", filename="disconnect_test.txt", file_size=1000),
        )
        await asyncio.sleep(0.05)

        ws_mock.is_connected = AsyncMock(return_value=False)
        await mgr.cleanup(cid)
        await asyncio.sleep(0.05)
        assert await mgr.get_active_count(cid) == 0

    @pytest.mark.asyncio
    async def test_get_active_count(self) -> None:
        """get_active_count returns correct values."""
        mgr, ws, _ = await _make_env()
        cid = "client-1"

        assert await mgr.get_active_count() == 0
        assert await mgr.get_active_count(cid) == 0

        await mgr.try_handle_message(
            cid,
            _make_msg("file.upload.start", filename="count.txt", file_size=10),
        )
        await asyncio.sleep(0.05)
        assert await mgr.get_active_count(cid) == 1
        assert await mgr.get_active_count() == 1


# ==========================================================================
# Backward Compatibility
# ==========================================================================


class TestBackwardCompat:
    """Non-file messages pass through."""

    @pytest.mark.asyncio
    async def test_ping_not_intercepted(self) -> None:
        """Ping messages are not intercepted."""
        mgr, _, _ = await _make_env()
        handled = await mgr.try_handle_message("c1", _make_msg("ping"))
        assert handled is False

    @pytest.mark.asyncio
    async def test_subscribe_not_intercepted(self) -> None:
        """Subscribe messages are not intercepted."""
        mgr, _, _ = await _make_env()
        handled = await mgr.try_handle_message("c1", _make_msg("subscribe", event="test"))
        assert handled is False

    @pytest.mark.asyncio
    async def test_command_not_intercepted(self) -> None:
        """Command messages are not intercepted."""
        mgr, _, _ = await _make_env()
        handled = await mgr.try_handle_message("c1", _make_msg("command.execute"))
        assert handled is False

    @pytest.mark.asyncio
    async def test_ai_stream_not_intercepted(self) -> None:
        """AI stream messages are not intercepted."""
        mgr, _, _ = await _make_env()
        handled = await mgr.try_handle_message("c1", _make_msg("ai.stream.start"))
        assert handled is False

    @pytest.mark.asyncio
    async def test_invalid_json_not_intercepted(self) -> None:
        """Invalid JSON is not intercepted."""
        mgr, _, _ = await _make_env()
        handled = await mgr.try_handle_message("c1", "not json{{{")
        assert handled is False

    @pytest.mark.asyncio
    async def test_unknown_msg_type_not_intercepted(self) -> None:
        """Unknown message types are not intercepted."""
        mgr, _, _ = await _make_env()
        handled = await mgr.try_handle_message("c1", _make_msg("some.random.type"))
        assert handled is False

    @pytest.mark.asyncio
    async def test_send_result_when_disconnected(self) -> None:
        """Sending result to disconnected client does not crash."""
        mgr, ws, _ = await _make_env()
        cid = "client-1"
        ws.is_connected = AsyncMock(return_value=False)

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("file.upload.start", filename="disc.txt", file_size=10),
        )
        assert handled is True
        await asyncio.sleep(0.05)


# ==========================================================================
# Edge Cases
# ==========================================================================


class TestEdgeCases:
    """Edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_empty_filename_path_traversal(self) -> None:
        """Path traversal in filename is prevented."""
        mgr, ws, _ = await _make_env()
        cid = "client-1"

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("file.upload.start", filename="../etc/passwd", file_size=10),
        )
        assert handled is True
        await asyncio.sleep(0.05)

        payload = _get_sent_payload(ws, 0)
        assert payload.get("filename") == "passwd"

    @pytest.mark.asyncio
    async def test_chunk_without_start(self) -> None:
        """Chunk message without active transfer is ignored."""
        mgr, ws, _ = await _make_env()
        cid = "client-1"

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("file.upload.chunk", transfer_id="no-such", data="AAAA", byte_offset=0),
        )
        assert handled is True
        await asyncio.sleep(0.05)
        assert ws.send.call_count == 0

    @pytest.mark.asyncio
    async def test_complete_without_transfer(self) -> None:
        """Complete message without active transfer is ignored."""
        mgr, ws, _ = await _make_env()
        cid = "client-1"

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("file.upload.complete", transfer_id="no-such"),
        )
        assert handled is True
        await asyncio.sleep(0.05)
        assert ws.send.call_count == 0

    @pytest.mark.asyncio
    async def test_cancel_other_client_transfer(self) -> None:
        """Cannot cancel another client's transfer."""
        mgr, ws, _ = await _make_env()
        cid1 = "client-1"
        cid2 = "client-2"

        await mgr.try_handle_message(
            cid1,
            _make_msg("file.upload.start", filename="other.txt", file_size=100),
        )
        await asyncio.sleep(0.05)

        tid = _get_sent_payload(ws, 0)["transfer_id"]
        ws.send.reset_mock()

        await mgr.try_handle_message(
            cid2,
            _make_msg("file.upload.cancel", transfer_id=tid),
        )
        await asyncio.sleep(0.05)
        assert await mgr.get_active_count(cid1) == 1
