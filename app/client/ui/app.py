from __future__ import annotations

import logging
from typing import Any, Optional

import customtkinter as ctk

from app.client.client import JarvisClient
from app.client.events import EventDispatcher
from app.client.state import ClientState
from app.client.ui.navigation import Navigator
from app.client.ui.theme import ThemeManager
from app.client.ui.window import MainWindow
from app.client.ui.worker import AsyncWorker
from app.core.config import Config

logger = logging.getLogger("jarvis.client.ui.app")


class DesktopApplication:
    def __init__(
        self,
        client: Optional[JarvisClient] = None,
        events: Optional[EventDispatcher] = None,
        state: Optional[ClientState] = None,
        theme: Optional[ThemeManager] = None,
        navigator: Optional[Navigator] = None,
        config: Optional[Config] = None,
        worker: Optional[AsyncWorker] = None,
    ):
        self._config = config or Config()
        self._events = events or EventDispatcher()
        self._client = client or JarvisClient(
            api_url=self._config.CLIENT_API_URL,
            ws_url=self._config.CLIENT_WS_URL,
            timeout=self._config.CLIENT_TIMEOUT,
            retry_count=self._config.CLIENT_RETRY_COUNT,
            heartbeat_interval=self._config.CLIENT_HEARTBEAT,
            auto_reconnect=self._config.CLIENT_AUTO_RECONNECT,
        )
        self._state = state or self._client.state
        self._theme = theme or ThemeManager(self._events)
        self._navigator = navigator if navigator is not None else Navigator(self._events)
        self._worker = worker or AsyncWorker()
        self._window: Optional[MainWindow] = None
        self._running = False
        self._shutdown_requested = False

        self._setup_logging()

    def _setup_logging(self) -> None:
        level = getattr(logging, self._config.CLIENT_LOG_LEVEL.upper(), logging.INFO)
        logging.getLogger("jarvis.client").setLevel(level)

    def run(self) -> None:
        self._running = True
        self._shutdown_requested = False

        ctk.set_appearance_mode(self._theme.mode.value)

        self._window = MainWindow(
            title=f"{self._config.APP_NAME} Desktop",
            theme=self._theme,
            navigator=self._navigator,
            state=self._state,
            events=self._events,
        )

        self._register_views()

        self._navigator.navigate("dashboard")

        self._events.publish("application.started")

        try:
            self._window.mainloop()
        except KeyboardInterrupt:
            pass
        finally:
            self._shutdown()

    def _register_views(self) -> None:
        from app.client.ui.pages.dashboard import DashboardView
        from app.client.ui.pages.chat import AIChatView
        from app.client.ui.pages.monitor import MonitorView
        from app.client.ui.pages.settings import SettingsView
        from app.client.ui.pages.skills import SkillsView

        views: list[tuple[str, type, str, str]] = [
            ("dashboard", DashboardView, "Dashboard", "🏠"),
            ("chat", AIChatView, "AI Chat", "💬"),
            ("monitor", MonitorView, "Monitor", "📊"),
            ("settings", SettingsView, "Settings", "⚙️"),
            ("skills", SkillsView, "Skills", "🧩"),
        ]
        for view_id, view_cls, title, icon in views:
            self._navigator.register_view(
                view_id,
                view_cls,
                title=title,
                icon=icon,
                client=self._client,
                worker=self._worker,
                config=self._config,
            )
            self._window.add_sidebar_item(view_id, title, icon)

    def register_view(self, view_id: str, view_class: type, **kwargs: Any) -> None:
        self._navigator.register_view(view_id, view_class, **kwargs)
        if self._window:
            self._window.add_sidebar_item(
                view_id=view_id,
                text=kwargs.get("title", view_id),
                icon=kwargs.get("icon", ""),
            )

    def navigate(self, view_id: str, **params: Any) -> bool:
        return self._navigator.navigate(view_id, **params)

    def shutdown(self) -> None:
        if self._shutdown_requested:
            return
        self._shutdown_requested = True
        if self._window:
            self._window.quit()
            self._window.update()
        self._shutdown()

    def _shutdown(self) -> None:
        if not self._running:
            return
        if self._navigator:
            self._navigator.destroy_all()
        if self._window:
            try:
                self._window.destroy()
            except Exception:
                pass
        if self._worker:
            self._worker.stop()
        if self._client:
            try:
                import asyncio
                try:
                    asyncio.run(asyncio.wait_for(self._client.disconnect(), timeout=2.0))
                except (RuntimeError, TypeError, asyncio.TimeoutError):
                    pass
            except Exception:
                pass
        self._running = False
        self._events.publish("application.stopped")

    @property
    def running(self) -> bool:
        return self._running

    @property
    def window(self) -> Optional[MainWindow]:
        return self._window

    @property
    def client(self) -> JarvisClient:
        return self._client

    @property
    def state(self) -> ClientState:
        return self._state

    @property
    def theme(self) -> ThemeManager:
        return self._theme

    @property
    def navigator(self) -> Navigator:
        return self._navigator

    @property
    def events(self) -> EventDispatcher:
        return self._events
