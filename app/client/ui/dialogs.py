from __future__ import annotations

from typing import Any, Callable, Optional

import customtkinter as ctk


def confirm(
    title: str = "Confirm",
    message: str = "Are you sure?",
    parent: Optional[Any] = None,
) -> bool:
    dialog = ctk.CTkInputDialog(
        text=message,
        title=title,
    )
    _ = dialog.get_input()
    result = getattr(dialog, "_result", None)
    return bool(result)


class InfoDialog(ctk.CTkToplevel):
    def __init__(
        self,
        parent: Optional[Any] = None,
        title: str = "Information",
        message: str = "",
        **kwargs: Any,
    ):
        super().__init__(parent, **kwargs)
        self.title(title)
        self.geometry("400x200")
        self.resizable(False, False)

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._label = ctk.CTkLabel(
            self,
            text=message,
            font=("Segoe UI", 12),
            wraplength=350,
        )
        self._label.grid(row=0, column=0, padx=20, pady=20, sticky="nsew")

        self._ok = ctk.CTkButton(self, text="OK", command=self.destroy, width=80)
        self._ok.grid(row=1, column=0, pady=(0, 16))


class ErrorDialog(ctk.CTkToplevel):
    def __init__(
        self,
        parent: Optional[Any] = None,
        title: str = "Error",
        message: str = "An error occurred.",
        detail: str = "",
        **kwargs: Any,
    ):
        super().__init__(parent, **kwargs)
        self.title(title)
        self.geometry("450x250")
        self.resizable(False, False)

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        header = ctk.CTkLabel(self, text="⚠", font=("Segoe UI", 24))
        header.grid(row=0, column=0, pady=(16, 0))

        self._label = ctk.CTkLabel(
            self,
            text=message,
            font=("Segoe UI", 12),
            wraplength=400,
        )
        self._label.grid(row=1, column=0, padx=20, pady=8, sticky="nsew")

        self._ok = ctk.CTkButton(self, text="OK", command=self.destroy, width=80)
        self._ok.grid(row=2, column=0, pady=(0, 16))


class WarningDialog(ctk.CTkToplevel):
    def __init__(
        self,
        parent: Optional[Any] = None,
        title: str = "Warning",
        message: str = "",
        **kwargs: Any,
    ):
        super().__init__(parent, **kwargs)
        self.title(title)
        self.geometry("400x200")
        self.resizable(False, False)

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        header = ctk.CTkLabel(self, text="⚠", font=("Segoe UI", 24))
        header.grid(row=0, column=0, pady=(16, 0))

        self._label = ctk.CTkLabel(
            self,
            text=message,
            font=("Segoe UI", 12),
            wraplength=350,
        )
        self._label.grid(row=1, column=0, padx=20, pady=8, sticky="nsew")

        self._ok = ctk.CTkButton(self, text="OK", command=self.destroy, width=80)
        self._ok.grid(row=2, column=0, pady=(0, 16))


class ProgressDialog(ctk.CTkToplevel):
    def __init__(
        self,
        parent: Optional[Any] = None,
        title: str = "Progress",
        message: str = "Working...",
        indeterminate: bool = True,
        **kwargs: Any,
    ):
        super().__init__(parent, **kwargs)
        self.title(title)
        self.geometry("350x150")
        self.resizable(False, False)

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._label = ctk.CTkLabel(self, text=message, font=("Segoe UI", 12))
        self._label.grid(row=0, column=0, padx=20, pady=(20, 8))

        self._progress = ctk.CTkProgressBar(self, mode="indeterminate" if indeterminate else "determinate", width=300)
        self._progress.grid(row=1, column=0, padx=20, pady=(0, 20))

        if indeterminate:
            self._progress.start()

    def set_message(self, text: str) -> None:
        self._label.configure(text=text)

    def set_progress(self, value: float) -> None:
        self._progress.set(value)

    def close(self) -> None:
        self.destroy()


class ReconnectDialog(ctk.CTkToplevel):
    def __init__(
        self,
        parent: Optional[Any] = None,
        title: str = "Reconnecting",
        message: str = "Connection lost. Reconnecting...",
        on_cancel: Optional[Callable] = None,
        **kwargs: Any,
    ):
        super().__init__(parent, **kwargs)
        self.title(title)
        self.geometry("350x150")
        self.resizable(False, False)

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._label = ctk.CTkLabel(self, text=message, font=("Segoe UI", 12))
        self._label.grid(row=0, column=0, padx=20, pady=(20, 8))

        self._progress = ctk.CTkProgressBar(self, mode="indeterminate", width=300)
        self._progress.grid(row=1, column=0, padx=20)
        self._progress.start()

        if on_cancel:
            self._cancel = ctk.CTkButton(
                self,
                text="Cancel",
                command=lambda: (on_cancel(), self.destroy()),
                width=80,
            )
            self._cancel.grid(row=2, column=0, pady=(8, 12))

    def set_message(self, text: str) -> None:
        self._label.configure(text=text)


class SettingsDialog(ctk.CTkToplevel):
    def __init__(
        self,
        parent: Optional[Any] = None,
        title: str = "Settings",
        settings: Optional[dict[str, Any]] = None,
        on_save: Optional[Callable] = None,
        **kwargs: Any,
    ):
        super().__init__(parent, **kwargs)
        self.title(title)
        self.geometry("500x400")
        self._settings = settings or {}
        self._on_save = on_save
        self._widgets: dict[str, Any] = {}

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(self)
        scroll.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        scroll.grid_columnconfigure(1, weight=1)

        row = 0
        for key, value in self._settings.items():
            label = ctk.CTkLabel(scroll, text=key, font=("Segoe UI", 11))
            label.grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)

            if isinstance(value, bool):
                widget = ctk.CTkSwitch(scroll, text="", onvalue=True, offvalue=False)
                widget.select() if value else widget.deselect()
                widget.grid(row=row, column=1, sticky="w", pady=4)
            else:
                widget = ctk.CTkEntry(scroll, font=("Segoe UI", 11))
                widget.insert(0, str(value))
                widget.grid(row=row, column=1, sticky="ew", pady=4)

            self._widgets[key] = widget
            row += 1

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=1, column=0, pady=(0, 10))

        save_btn = ctk.CTkButton(
            btn_frame,
            text="Save",
            command=self._save,
            width=80,
        )
        save_btn.pack(side="left", padx=4)

        cancel_btn = ctk.CTkButton(
            btn_frame,
            text="Cancel",
            command=self.destroy,
            width=80,
        )
        cancel_btn.pack(side="left", padx=4)

    def _save(self) -> None:
        result = {}
        for key, widget in self._widgets.items():
            if isinstance(widget, ctk.CTkSwitch):
                result[key] = widget.get() == 1
            else:
                result[key] = widget.get()
        if self._on_save:
            self._on_save(result)
        self.destroy()
