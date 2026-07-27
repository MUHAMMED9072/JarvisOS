from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(tags=["WebSocket Observability"])


def _get_svc(request: Request, attr: str):
    svc = getattr(request.app.state, attr, None)
    if svc is None:
        raise HTTPException(status_code=503, detail=f"{attr} not available")
    return svc


@router.get("/api/v1/ws/metrics")
async def get_ws_metrics(request: Request):
    """Return current WebSocket metrics."""
    svc = _get_svc(request, "ws_metrics")
    return await svc.snapshot()


@router.get("/api/v1/ws/health")
async def get_ws_health(request: Request):
    """Return current WebSocket health status."""
    svc = _get_svc(request, "ws_health")
    return await svc.evaluate()


@router.get("/api/v1/ws/diagnostics")
async def get_ws_diagnostics(request: Request):
    """Return a comprehensive WebSocket diagnostics report."""
    svc = _get_svc(request, "ws_diagnostics")
    return await svc.generate()
