from __future__ import annotations

import logging
import time
from typing import Any, Optional

import customtkinter as ctk

from app.client.client import JarvisClient
from app.client.ui.base_view import BaseView
from app.client.ui.models import MetricSample
from app.client.ui.worker import AsyncWorker

logger = logging.getLogger("jarvis.client.ui.pages.monitor")


class MonitorView(BaseView):
    def __init__(
        self,
        master: Any,
        client: Optional[JarvisClient] = None,
        worker: Optional[AsyncWorker] = None,
        **kwargs: Any,
    ):
        super().__init__(master, **kwargs)
        self._client = client
        self._worker = worker
        self._sample = MetricSample()
        self._history: list[MetricSample] = []
        self._refresh_job: str | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=0)
        self.grid_rowconfigure(2, weight=1)
        self.grid_rowconfigure(3, weight=0)
        self.grid_columnconfigure(0, weight=1)

        header = ctk.CTkLabel(
            self,
            text="System Monitor",
            font=("Segoe UI", 22, "bold"),
            anchor="w",
        )
        header.grid(row=0, column=0, sticky="w", padx=20, pady=(16, 8))

        metrics_frame = ctk.CTkFrame(self)
        metrics_frame.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 8))
        metrics_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self._cpu_label = self._make_metric_display(metrics_frame, "CPU", "0%", 0)
        self._memory_label = self._make_metric_display(metrics_frame, "Memory", "0%", 1)
        self._disk_label = self._make_metric_display(metrics_frame, "Disk", "0%", 2)
        self._network_label = self._make_metric_display(metrics_frame, "Network", "0 Mbps", 3)

        details_frame = ctk.CTkFrame(self)
        details_frame.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 8))
        details_frame.grid_rowconfigure(0, weight=1)
        details_frame.grid_columnconfigure(0, weight=1)

        self._details_text = ctk.CTkTextbox(details_frame, wrap="word", font=("Segoe UI", 11))
        self._details_text.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self._details_text.configure(state="disabled")

        controls_frame = ctk.CTkFrame(self)
        controls_frame.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 16))
        controls_frame.grid_columnconfigure(0, weight=1)

        self._refresh_btn = ctk.CTkButton(
            controls_frame,
            text="Refresh Now",
            command=self._refresh_metrics,
            width=120,
        )
        self._refresh_btn.grid(row=0, column=0, padx=6, pady=8, sticky="w")

        self._auto_refresh_var = ctk.StringVar(value="off")
        self._auto_refresh_toggle = ctk.CTkSwitch(
            controls_frame,
            text="Auto-refresh",
            command=self._toggle_auto_refresh,
            variable=self._auto_refresh_var,
            onvalue="on",
            offvalue="off",
        )
        self._auto_refresh_toggle.grid(row=0, column=1, padx=6, pady=8, sticky="w")

        self._status_label = ctk.CTkLabel(
            controls_frame,
            text="",
            font=("Segoe UI", 10),
        )
        self._status_label.grid(row=0, column=2, padx=6, pady=8, sticky="e")

    def _make_metric_display(
        self,
        parent: Any,
        label: str,
        value: str,
        col: int,
    ) -> ctk.CTkLabel:
        frame = ctk.CTkFrame(parent)
        frame.grid(row=0, column=col, sticky="nsew", padx=4, pady=8)
        frame.grid_rowconfigure(0, weight=0)
        frame.grid_rowconfigure(1, weight=0)
        frame.grid_columnconfigure(0, weight=1)

        lbl = ctk.CTkLabel(frame, text=label, font=("Segoe UI", 10))
        lbl.grid(row=0, column=0, padx=8, pady=(8, 0))

        val = ctk.CTkLabel(frame, text=value, font=("Segoe UI", 20, "bold"))
        val.grid(row=1, column=0, padx=8, pady=(0, 8))

        frame._value_label = val
        return frame._value_label

    def _refresh_metrics(self) -> None:
        if not self._client or not self._worker:
            return
        self._status_label.configure(text="Fetching...")

        async def do_fetch():
            try:
                health = await self._client.fetch_health()
                status_data = await self._client.rest.status()
                return status_data
            except Exception as exc:
                return {"error": str(exc)}

        def done(result: Any, error: str = "") -> None:
            if error:
                self._status_label.configure(text=f"Error: {error}")
                return
            if result and isinstance(result, dict):
                if "error" in result:
                    self._status_label.configure(text=f"Error: {result['error']}")
                    return
                self._update_from_status(result)
            self._status_label.configure(text=f"Last updated: {time.strftime('%H:%M:%S')}")

        self._worker.run(do_fetch(), done)

    def _update_from_status(self, data: dict[str, Any]) -> None:
        cpu = data.get("cpu_percent", data.get("cpu", 0))
        mem = data.get("memory_percent", data.get("memory", 0))
        disk = data.get("disk_percent", data.get("disk", 0))
        net = data.get("network_mbps", data.get("network", 0))

        self._cpu_label.configure(text=f"{cpu}%")
        self._memory_label.configure(text=f"{mem}%")
        self._disk_label.configure(text=f"{disk}%")
        self._network_label.configure(text=f"{net} Mbps")

        self._details_text.configure(state="normal")
        self._details_text.delete("0.0", "end")
        for key, value in data.items():
            if not key.startswith("_"):
                self._details_text.insert("end", f"{key}: {value}\n")
        self._details_text.see("end")
        self._details_text.configure(state="disabled")

    def _toggle_auto_refresh(self) -> None:
        if self._auto_refresh_var.get() == "on":
            self._start_auto_refresh()
        else:
            self._stop_auto_refresh()

    def _start_auto_refresh(self) -> None:
        self._refresh_metrics()

    def _stop_auto_refresh(self) -> None:
        pass

    def on_refresh(self) -> None:
        self._refresh_metrics()

    def on_hide(self) -> None:
        self._stop_auto_refresh()

    def on_destroy(self) -> None:
        self._stop_auto_refresh()
        self._history.clear()
        super().on_destroy()
