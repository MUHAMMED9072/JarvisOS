from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from app.client.events import EventDispatcher

logger = logging.getLogger("jarvis.client.ui.navigation")


class NavigationHistory:
    def __init__(self, maxlen: int = 50):
        self._back: list[str] = []
        self._forward: list[str] = []
        self._maxlen = maxlen

    def push(self, view_id: str) -> None:
        self._back.append(view_id)
        if len(self._back) > self._maxlen:
            self._back.pop(0)
        self._forward.clear()

    def can_go_back(self) -> bool:
        return len(self._back) > 0

    def can_go_forward(self) -> bool:
        return len(self._forward) > 0

    def go_back(self) -> Optional[str]:
        if not self._back:
            return None
        return self._back.pop()

    def go_forward(self) -> Optional[str]:
        if not self._forward:
            return None
        return self._forward.pop()

    @property
    def current(self) -> Optional[str]:
        return self._back[-1] if self._back else None

    @property
    def length(self) -> int:
        return len(self._back)

    def clear(self) -> None:
        self._back.clear()
        self._forward.clear()


class Navigator:
    def __init__(self, events: Optional[EventDispatcher] = None):
        self._events = events or EventDispatcher()
        self._registry: dict[str, dict] = {}
        self._history = NavigationHistory()
        self._active: Optional[str] = None
        self._container: Optional[Any] = None

    def set_container(self, container: Any) -> None:
        self._container = container

    def register_view(
        self,
        view_id: str,
        view_class: type,
        title: str = "",
        icon: str = "",
        lazy: bool = True,
        **kwargs: Any,
    ) -> None:
        self._registry[view_id] = {
            "class": view_class,
            "title": title,
            "icon": icon,
            "lazy": lazy,
            "instance": None,
            "kwargs": kwargs,
        }
        self._events.publish("navigation.view.registered", view_id=view_id, title=title)

    def unregister_view(self, view_id: str) -> None:
        entry = self._registry.pop(view_id, None)
        if entry and entry["instance"]:
            entry["instance"].on_destroy()
        self._events.publish("navigation.view.unregistered", view_id=view_id)

    def navigate(self, view_id: str, **params: Any) -> bool:
        entry = self._registry.get(view_id)
        if not entry:
            logger.warning("View not registered: %s", view_id)
            return False

        if self._active:
            current = self._registry.get(self._active)
            if current and current["instance"]:
                current["instance"].on_hide()
            self._history.push(self._active)

        if entry["lazy"] and entry["instance"] is None:
            try:
                entry["instance"] = entry["class"](
                    master=self._container,
                    navigator=self,
                    events=self._events,
                    **entry["kwargs"],
                )
            except Exception as exc:
                logger.error("Failed to load view %s: %s", view_id, exc)
                return False

        instance = entry["instance"]
        if instance is None:
            return False

        self._active = view_id

        if self._container:
            for child in self._container.winfo_children():
                child.grid_remove()

        instance.grid(row=0, column=0, sticky="nsew")
        instance.on_show(**params)

        self._events.publish(
            "navigation.changed",
            view_id=view_id,
            title=entry["title"],
        )
        return True

    def go_back(self) -> bool:
        if not self._history.can_go_back():
            return False
        # Push current active to forward before navigating back
        if self._active:
            target = self._history.go_back()
            if target is None:
                return False
            # Save current as the "forward" destination
            self._history._forward.append(self._active)
            return self._navigate_history(target)
        return False

    def go_forward(self) -> bool:
        if not self._history.can_go_forward():
            return False
        if self._active:
            target = self._history.go_forward()
            if target is None:
                return False
            self._history._back.append(self._active)
            return self._navigate_history(target)
        return False

    def _navigate_history(self, view_id: str) -> bool:
        entry = self._registry.get(view_id)
        if not entry or not entry["instance"]:
            return False

        if self._active:
            current = self._registry.get(self._active)
            if current and current["instance"]:
                current["instance"].on_hide()

        self._active = view_id

        if self._container:
            for child in self._container.winfo_children():
                child.grid_remove()

        entry["instance"].grid(row=0, column=0, sticky="nsew")
        entry["instance"].on_show()
        self._events.publish("navigation.changed", view_id=view_id, title=entry["title"])
        return True

    @property
    def active_view(self) -> Optional[str]:
        return self._active

    @property
    def active_instance(self) -> Optional[Any]:
        if self._active:
            entry = self._registry.get(self._active)
            if entry:
                return entry["instance"]
        return None

    @property
    def can_go_back(self) -> bool:
        return self._history.can_go_back()

    @property
    def can_go_forward(self) -> bool:
        return self._history.can_go_forward()

    def get_view(self, view_id: str) -> Optional[Any]:
        entry = self._registry.get(view_id)
        return entry["instance"] if entry else None

    def get_title(self, view_id: str) -> str:
        entry = self._registry.get(view_id)
        return entry["title"] if entry else ""

    def registered_views(self) -> list[dict]:
        return [
            {
                "id": vid,
                "title": v["title"],
                "icon": v["icon"],
                "loaded": v["instance"] is not None,
            }
            for vid, v in self._registry.items()
        ]

    def refresh_active(self) -> None:
        if self._active:
            entry = self._registry.get(self._active)
            if entry and entry["instance"]:
                entry["instance"].on_refresh()

    def destroy_all(self) -> None:
        for entry in self._registry.values():
            if entry["instance"]:
                try:
                    entry["instance"].on_destroy()
                except Exception:
                    logger.debug("Error destroying view", exc_info=True)
        self._registry.clear()
        self._history.clear()
        self._active = None

    def __len__(self) -> int:
        return len(self._registry)
