from __future__ import annotations

from typing import Any, Callable, Optional

import customtkinter as ctk

from app.client.ui.theme import ThemeManager


class StatusCard(ctk.CTkFrame):
    def __init__(
        self,
        master: Any,
        title: str = "",
        value: str = "",
        status: str = "info",
        theme: Optional[ThemeManager] = None,
        **kwargs: Any,
    ):
        super().__init__(master, **kwargs)
        self._theme = theme
        self._title_str = title
        self._value_str = value
        self._status = status

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)

        self._title_label = ctk.CTkLabel(
            self,
            text=title,
            font=("Segoe UI", 10),
            anchor="w",
        )
        self._title_label.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 0))

        self._value_label = ctk.CTkLabel(
            self,
            text=value,
            font=("Segoe UI", 18, "bold"),
            anchor="w",
        )
        self._value_label.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))

    def set_value(self, text: str) -> None:
        self._value_label.configure(text=text)

    def set_title(self, text: str) -> None:
        self._title_label.configure(text=text)

    def set_status(self, status: str) -> None:
        self._status = status


class MetricCard(ctk.CTkFrame):
    def __init__(
        self,
        master: Any,
        label: str = "",
        value: str = "0",
        unit: str = "",
        icon: str = "",
        **kwargs: Any,
    ):
        super().__init__(master, **kwargs)
        self._label_text = label
        self._value_text = value
        self._unit_text = unit
        self._icon_text = icon

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)

        self._value_label = ctk.CTkLabel(
            self,
            text=f"{value}{unit}",
            font=("Segoe UI", 22, "bold"),
        )
        self._value_label.grid(row=0, column=0, sticky="nsew", padx=8, pady=(8, 0))

        self._label_widget = ctk.CTkLabel(
            self,
            text=label,
            font=("Segoe UI", 10),
        )
        self._label_widget.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))

    def set_value(self, value: str) -> None:
        self._value_label.configure(text=f"{value}{self._unit_text}")

    def set_label(self, text: str) -> None:
        self._label_widget.configure(text=text)

    def set_unit(self, unit: str) -> None:
        self._unit_text = unit


class ConnectionIndicator(ctk.CTkFrame):
    def __init__(self, master: Any, **kwargs: Any):
        super().__init__(master, **kwargs)
        self._status = "disconnected"
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)

        self._dot = ctk.CTkLabel(self, text="●", font=("Segoe UI", 10))
        self._dot.grid(row=0, column=0, padx=(4, 2))

        self._label = ctk.CTkLabel(self, text="Disconnected", font=("Segoe UI", 10))
        self._label.grid(row=0, column=1, padx=(2, 4))

    def set_status(self, status: str) -> None:
        self._status = status
        color_map = {
            "connected": "#00e676",
            "connecting": "#ffd740",
            "disconnected": "#ff5252",
            "reconnecting": "#ffd740",
            "error": "#ff5252",
        }
        label_map = {
            "connected": "Connected",
            "connecting": "Connecting...",
            "disconnected": "Disconnected",
            "reconnecting": "Reconnecting...",
            "error": "Error",
        }
        color = color_map.get(status, "#a0a0a0")
        label = label_map.get(status, status.capitalize())
        self._dot.configure(text_color=color)
        self._label.configure(text=label)

    @property
    def status(self) -> str:
        return self._status


class LoadingOverlay(ctk.CTkFrame):
    def __init__(self, master: Any, message: str = "Loading...", **kwargs: Any):
        super().__init__(master, **kwargs)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        inner = ctk.CTkFrame(self, fg_color="transparent")
        inner.grid(row=0, column=0)

        self._spinner = ctk.CTkProgressBar(inner, mode="indeterminate", width=200)
        self._spinner.grid(row=0, column=0, pady=(0, 8))
        self._spinner.start()

        self._message = ctk.CTkLabel(inner, text=message, font=("Segoe UI", 12))
        self._message.grid(row=1, column=0)

    def set_message(self, text: str) -> None:
        self._message.configure(text=text)


class Toolbar(ctk.CTkFrame):
    def __init__(self, master: Any, **kwargs: Any):
        super().__init__(master, height=40, **kwargs)
        self.grid_propagate(False)
        self.grid_columnconfigure(0, weight=1)
        self._items: dict[str, ctk.CTkButton] = {}
        self._left_items: list[ctk.CTkButton] = []
        self._right_items: list[ctk.CTkButton] = []
        self._next_left = 0
        self._next_right = 0

    def add_left(self, text: str, command: Optional[Callable] = None) -> ctk.CTkButton:
        btn = ctk.CTkButton(
            self,
            text=text,
            command=command,
            height=28,
            font=("Segoe UI", 11),
        )
        btn.grid(row=0, column=self._next_left, padx=2, pady=4, sticky="w")
        self._next_left += 1
        self._items[text] = btn
        return btn

    def add_right(self, text: str, command: Optional[Callable] = None) -> ctk.CTkButton:
        btn = ctk.CTkButton(
            self,
            text=text,
            command=command,
            height=28,
            font=("Segoe UI", 11),
        )
        self._right_items.append(btn)
        col = 100 + len(self._right_items)
        btn.grid(row=0, column=col, padx=2, pady=4, sticky="e")
        return btn


class SidebarItem(ctk.CTkFrame):
    def __init__(
        self,
        master: Any,
        text: str = "",
        icon: str = "",
        command: Optional[Callable] = None,
        active: bool = False,
        **kwargs: Any,
    ):
        super().__init__(master, **kwargs)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self._active = active

        icon_text = icon or "○"
        self._icon_label = ctk.CTkLabel(self, text=icon_text, font=("Segoe UI", 12), width=20)
        self._icon_label.grid(row=0, column=0, padx=(8, 4), pady=6)

        self._text_label = ctk.CTkLabel(
            self,
            text=text,
            font=("Segoe UI", 12),
            anchor="w",
        )
        self._text_label.grid(row=0, column=1, padx=(4, 8), pady=6, sticky="ew")

        if command:
            self._text_label.bind("<Button-1>", lambda e: command())
            self._icon_label.bind("<Button-1>", lambda e: command())
            self.bind("<Button-1>", lambda e: command())

        self._update_appearance()

    def set_active(self, active: bool) -> None:
        self._active = active
        self._update_appearance()

    def _update_appearance(self) -> None:
        pass

    def set_text(self, text: str) -> None:
        self._text_label.configure(text=text)


class SearchBox(ctk.CTkFrame):
    def __init__(
        self,
        master: Any,
        placeholder: str = "Search...",
        command: Optional[Callable] = None,
        **kwargs: Any,
    ):
        super().__init__(master, **kwargs)
        self.grid_columnconfigure(0, weight=1)

        self._entry = ctk.CTkEntry(
            self,
            placeholder_text=placeholder,
            font=("Segoe UI", 12),
        )
        self._entry.grid(row=0, column=0, sticky="ew", padx=4, pady=4)

        if command:
            self._entry.bind("<Return>", lambda e: command(self._entry.get()))

    def get_text(self) -> str:
        return self._entry.get()

    def set_text(self, text: str) -> None:
        self._entry.delete(0, "end")
        self._entry.insert(0, text)

    def clear(self) -> None:
        self._entry.delete(0, "end")


class EmptyState(ctk.CTkFrame):
    def __init__(
        self,
        master: Any,
        title: str = "No Data",
        message: str = "Nothing to display yet.",
        icon: str = "📭",
        **kwargs: Any,
    ):
        super().__init__(master, **kwargs)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        inner = ctk.CTkFrame(self, fg_color="transparent")
        inner.grid(row=0, column=0)

        self._icon_label = ctk.CTkLabel(inner, text=icon, font=("Segoe UI", 36))
        self._icon_label.grid(row=0, column=0, pady=(0, 8))

        self._title_label = ctk.CTkLabel(
            inner,
            text=title,
            font=("Segoe UI", 16, "bold"),
        )
        self._title_label.grid(row=1, column=0, pady=(0, 4))

        self._message_label = ctk.CTkLabel(
            inner,
            text=message,
            font=("Segoe UI", 11),
            text_color="gray",
        )
        self._message_label.grid(row=2, column=0)

    def set_title(self, text: str) -> None:
        self._title_label.configure(text=text)

    def set_message(self, text: str) -> None:
        self._message_label.configure(text=text)


class ErrorView(ctk.CTkFrame):
    def __init__(
        self,
        master: Any,
        title: str = "Error",
        message: str = "An unexpected error occurred.",
        on_retry: Optional[Callable] = None,
        **kwargs: Any,
    ):
        super().__init__(master, **kwargs)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        inner = ctk.CTkFrame(self, fg_color="transparent")
        inner.grid(row=0, column=0)

        self._icon_label = ctk.CTkLabel(inner, text="⚠", font=("Segoe UI", 36))
        self._icon_label.grid(row=0, column=0, pady=(0, 8))

        self._title_label = ctk.CTkLabel(
            inner,
            text=title,
            font=("Segoe UI", 16, "bold"),
        )
        self._title_label.grid(row=1, column=0, pady=(0, 4))

        self._message_label = ctk.CTkLabel(
            inner,
            text=message,
            font=("Segoe UI", 11),
            text_color="gray",
            wraplength=400,
        )
        self._message_label.grid(row=2, column=0, pady=(0, 12))

        if on_retry:
            self._retry_btn = ctk.CTkButton(
                inner,
                text="Retry",
                command=on_retry,
                width=100,
            )
            self._retry_btn.grid(row=3, column=0)

    def set_message(self, text: str) -> None:
        self._message_label.configure(text=text)
