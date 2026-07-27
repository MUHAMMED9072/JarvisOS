from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Optional

from app.client.events import EventDispatcher
from app.client.state import ClientState
from app.client.ui.theme import ThemeManager

logger = logging.getLogger("jarvis.client.ui.bindings")


class StateBinding:
    def __init__(
        self,
        state: ClientState,
        events: EventDispatcher,
        theme: Optional[ThemeManager] = None,
    ):
        self._state = state
        self._events = events
        self._theme = theme or ThemeManager(events)
        self._subscriptions: dict[str, list[Callable]] = {}
        self._bound_widgets: dict[str, list[tuple[Any, str, Callable]]] = {}
        self._lock = threading.RLock()

    def bind(
        self,
        widget: Any,
        state_key: str,
        widget_attr: str = "configure",
        transform: Optional[Callable] = None,
    ) -> None:
        with self._lock:
            if state_key not in self._subscriptions:
                self._subscriptions[state_key] = []

            def handler(event: str, **data: Any) -> None:
                value = getattr(self._state, state_key, None)
                if transform:
                    value = transform(value)
                final = value if value is not None else ""
                self._safe_update(widget, widget_attr, final)

            self._subscriptions[state_key].append(handler)
            self._events.subscribe(f"state.{state_key}", handler)

            if state_key not in self._bound_widgets:
                self._bound_widgets[state_key] = []
            self._bound_widgets[state_key].append((widget, widget_attr, handler))

            initial = getattr(self._state, state_key, None)
            if initial is not None:
                if transform:
                    initial = transform(initial)
                self._safe_update(widget, widget_attr, initial)

    def bind_text(self, widget: Any, state_key: str) -> None:
        def _set_text(value: Any) -> None:
            widget.configure(text=str(value) if value is not None else "")

        with self._lock:
            state_event = f"state.{state_key}"

            def handler(event: str, **data: Any) -> None:
                value = getattr(self._state, state_key, None)
                self._safe_call(_set_text, value)

            self._subscriptions.setdefault(state_key, []).append(handler)
            self._events.subscribe(state_event, handler)
            self._bound_widgets.setdefault(state_key, []).append(
                (widget, "text", handler)
            )

            initial = getattr(self._state, state_key, None)
            self._safe_call(_set_text, initial)

    def bind_enabled(self, widget: Any, state_key: str, invert: bool = False) -> None:
        with self._lock:
            state_event = f"state.{state_key}"

            def handler(event: str, **data: Any) -> None:
                val = getattr(self._state, state_key, False)
                state = not val if invert else bool(val)
                self._safe_update(widget, "configure", {"state": "normal" if state else "disabled"})

            self._subscriptions.setdefault(state_key, []).append(handler)
            self._events.subscribe(state_event, handler)
            self._bound_widgets.setdefault(state_key, []).append(
                (widget, "enabled", handler)
            )

    def bind_visible(self, widget: Any, state_key: str, invert: bool = False) -> None:
        with self._lock:
            state_event = f"state.{state_key}"

            def handler(event: str, **data: Any) -> None:
                val = getattr(self._state, state_key, False)
                visible = not val if invert else bool(val)
                self._safe_update(widget, "grid" if visible else "grid_remove", {})

            self._subscriptions.setdefault(state_key, []).append(handler)
            self._events.subscribe(state_event, handler)
            self._bound_widgets.setdefault(state_key, []).append(
                (widget, "visible", handler)
            )

    def unbind_all(self) -> None:
        with self._lock:
            for state_key, handlers in self._subscriptions.items():
                for handler in handlers:
                    self._events.unsubscribe(f"state.{state_key}", handler)
            self._subscriptions.clear()
            self._bound_widgets.clear()

    def unbind_widget(self, widget: Any) -> None:
        with self._lock:
            to_remove: list[str] = []
            for state_key, widgets in self._bound_widgets.items():
                remaining = [(w, attr, h) for w, attr, h in widgets if w is not widget]
                removed = len(widgets) - len(remaining)
                if removed > 0:
                    for w, attr, h in widgets:
                        if w is widget:
                            self._events.unsubscribe(f"state.{state_key}", h)
                if remaining:
                    self._bound_widgets[state_key] = remaining
                else:
                    to_remove.append(state_key)
            for k in to_remove:
                del self._bound_widgets[k]

    def _safe_update(self, widget: Any, attr: str, value: Any) -> None:
        def update():
            try:
                if attr == "configure":
                    if isinstance(value, dict):
                        widget.configure(**value)
                    else:
                        widget.configure(text=str(value))
                elif attr == "text":
                    widget.configure(text=str(value))
                elif attr == "grid":
                    widget.grid()
                elif attr == "grid_remove":
                    widget.grid_remove()
                else:
                    setattr(widget, attr, value)
            except Exception:
                logger.debug("UI update failed", exc_info=True)

        self._safe_call(update)

    def _safe_call(self, fn: Callable, *args: Any, **kwargs: Any) -> None:
        try:
            if threading.current_thread() is threading.main_thread():
                fn(*args, **kwargs)
            else:
                try:
                    import customtkinter as ctk
                    if ctk.get_ctk_root():
                        ctk.get_ctk_root().after(0, fn, *args, **kwargs)
                except Exception:
                    fn(*args, **kwargs)
        except Exception:
            logger.debug("Error in UI callback", exc_info=True)
