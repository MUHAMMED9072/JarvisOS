from fastapi import FastAPI


def register_routes(app: FastAPI) -> None:
    """Register all API route modules on the application."""
    from app.api.routes.health import router as health_router
    from app.api.routes.status import router as status_router
    from app.api.routes.config import router as config_router
    from app.api.routes.services import router as services_router
    from app.api.routes.ai import router as ai_router
    from app.api.routes.skills import router as skills_router
    from app.api.routes.plugins import router as plugins_router
    from app.api.routes.voice import router as voice_router

    app.include_router(health_router, prefix="/api/v1")
    app.include_router(status_router, prefix="/api/v1")
    app.include_router(config_router, prefix="/api/v1")
    app.include_router(services_router, prefix="/api/v1")
    app.include_router(ai_router)
    app.include_router(skills_router)
    app.include_router(plugins_router)
    app.include_router(voice_router)
