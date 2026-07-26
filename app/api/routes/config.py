from __future__ import annotations

from fastapi import APIRouter

from app.api.schemas import ConfigResponse
from app.core.config import Config

router = APIRouter(tags=["Configuration"])


@router.get("/config", response_model=ConfigResponse)
async def get_config() -> ConfigResponse:
    """Return the current read-only configuration."""
    return ConfigResponse(
        app_name=Config.APP_NAME,
        version=Config.VERSION,
        data_dir=str(Config.DATA_DIR),
        plugin_dir=str(Config.PLUGIN_DIR),
        log_level=Config.LOG_LEVEL,
        default_brain=Config.DEFAULT_BRAIN,
        voice_enabled=Config.VOICE.enabled,
        wake_word=Config.WAKE_WORD,
    )
