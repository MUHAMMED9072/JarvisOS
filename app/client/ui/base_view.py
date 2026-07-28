from __future__ import annotations

import logging
from typing import Any, Optional

import customtkinter as ctk

from app.client.events import EventDispatcher
from app.client.state import ClientState
from app.client.ui.bindings import StateBinding
from app.client.ui.theme import ThemeManager

logger = logging.getLogger("jarvis.client.ui.views")


class BaseView(ctk.CTkFrame):
    def __init__(
        self,
        master: Any,
        navigator: Any = None,
        events: Optional[EventDispatcher] = None,
        state: Optional[ClientState] = None,
        theme: Optional[ThemeManager] = None,
        **kwargs: Any,
    ):
        super().__init__(master, **kwargs)
        self._navigator = navigator
        self._events = events or EventDispatcher()
        self._state = state
        self._theme = theme or ThemeManager(self._events)
        self._bindings: Optional[StateBinding] = None
        self._loaded = False
        self._subscriptions: list[tuple[str, Any]] = []

        if state:
            self._bindings = StateBinding(state, self._events, self._theme)

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

    @property
    def navigator(self) -> Any:
        return self._navigator

    @property
    def events(self) -> EventDispatcher:
        return self._events

    @property
    def state(self) -> Optional[ClientState]:
        return self._state

    @property
    def theme(self) -> ThemeManager:
        return self._theme

    @property
    def bindings(self) -> Optional[StateBinding]:
        return self._bindings

    def on_load(self) -> None:
        pass

    def on_show(self, **params: Any) -> None:
        if not self._loaded:
            self._loaded = True
            self.on_load()
        self.on_refresh()

    def on_hide(self) -> None:
        pass

    def on_refresh(self) -> None:
        pass

    def on_destroy(self) -> None:
        self._cleanup_bindings()
        self._cleanup_subscriptions()

    def _cleanup_bindings(self) -> None:
        if self._bindings:
            self._bindings.unbind_all()
            self._bindings = None

    def _cleanup_subscriptions(self) -> None:
        for event, handler in self._subscriptions:
            self._events.unsubscribe(event, handler)
        self._subscriptions.clear()

    def subscribe(self, event: str, handler: Any) -> None:
        self._events.subscribe(event, handler)
        self._subscriptions.append((event, handler))

    def destroy(self) -> None:
        self.on_destroy()
        super().destroy()


class PlaceholderView(BaseView):
    def __init__(self, master: Any, title: str = "Coming Soon", **kwargs: Any):
        super().__init__(master, **kwargs)
        self._title = title
        self._build_ui()

    def _build_ui(self) -> None:
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._label = ctk.CTkLabel(
            self,
            text=self._title,
            font=("Segoe UI", 24, "bold"),
        )
        self._label.grid(row=0, column=0, sticky="nsew", padx=40, pady=40)

    def on_refresh(self) -> None:
        pass
