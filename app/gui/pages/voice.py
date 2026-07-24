from __future__ import annotations

import datetime

import customtkinter as ctk

from app.core.registry import ServiceRegistry
from app.gui.controllers.voice_controller import VoiceController
from app.gui.pages.base_page import BasePage
from app.gui.theme import COLORS


class VoicePage(BasePage):
    """Voice control page with status, live display, and actions."""

    name = "voice"
    title = "Voice"

    def __init__(self, master, registry: ServiceRegistry) -> None:
        super().__init__(master, registry)

        self._ctrl = VoiceController(registry)

        # Attach live callbacks
        self._ctrl.on_transcript = self._on_transcript_cb
        self._ctrl.on_response = self._on_response_cb
        self._ctrl.on_error = self._on_error_cb
        self._ctrl.on_wake = self._on_wake_cb
        self._ctrl.on_running_changed = self._on_running_changed_cb

        # Two-column layout
        self.grid_columnconfigure(0, weight=2, minsize=500)
        self.grid_columnconfigure(1, weight=1, minsize=280)

        self._build_status_card()
        self._build_live_area()
        self._build_speak_input()
        self._build_activity_log()

        self._timer_id: str | None = None

    # ==================================================================
    # Status card (left column, row 0)
    # ==================================================================

    def _build_status_card(self) -> None:
        card = ctk.CTkFrame(
            self,
            corner_radius=15,
            fg_color=COLORS["card"],
        )
        card.grid(row=0, column=0, sticky="nsew", padx=(40, 10), pady=(30, 10))
        card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            card,
            text="Voice Engine",
            font=("Segoe UI", 20, "bold"),
            text_color="white",
            anchor="w",
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=20, pady=(20, 10))

        self._status_label = ctk.CTkLabel(
            card,
            text="Status: Checking...",
            font=("Segoe UI", 14),
            text_color=COLORS["text"],
            anchor="w",
        )
        self._status_label.grid(row=1, column=0, sticky="w", padx=20, pady=2)

        self._wake_label = ctk.CTkLabel(
            card,
            text="Wake Word: --",
            font=("Segoe UI", 14),
            text_color=COLORS["text"],
            anchor="w",
        )
        self._wake_label.grid(row=2, column=0, sticky="w", padx=20, pady=2)

        self._toggle_btn = ctk.CTkButton(
            card,
            text="Start",
            width=100,
            height=32,
            font=("Segoe UI", 13),
            fg_color=COLORS["success"],
            text_color=COLORS["background"],
            hover_color="#1DA44E",
            command=self._toggle_running,
        )
        self._toggle_btn.grid(row=1, column=2, rowspan=2, padx=(0, 20), sticky="e")

    # ==================================================================
    # Live transcript / response display (left column, row 1)
    # ==================================================================

    def _build_live_area(self) -> None:
        frame = ctk.CTkFrame(
            self,
            corner_radius=15,
            fg_color=COLORS["card"],
        )
        frame.grid(row=1, column=0, sticky="nsew", padx=(40, 10), pady=(10, 10))
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            frame,
            text="Live Activity",
            font=("Segoe UI", 16, "bold"),
            text_color="white",
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(15, 5))

        self._live_text = ctk.CTkTextbox(
            frame,
            font=("Consolas", 13),
            fg_color=COLORS["background"],
            text_color=COLORS["text"],
            wrap="word",
            height=120,
        )
        self._live_text.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0, 15))
        self._live_text.configure(state="disabled")

    # ==================================================================
    # Speak input (left column, row 2)
    # ==================================================================

    def _build_speak_input(self) -> None:
        frame = ctk.CTkFrame(
            self,
            corner_radius=15,
            fg_color=COLORS["card"],
        )
        frame.grid(row=2, column=0, sticky="nsew", padx=(40, 10), pady=(10, 30))
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            frame,
            text="Type to Speak",
            font=("Segoe UI", 16, "bold"),
            text_color="white",
            anchor="w",
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=20, pady=(15, 10))

        self._speak_entry = ctk.CTkEntry(
            frame,
            placeholder_text="Type something for the assistant to say...",
            font=("Segoe UI", 13),
            fg_color=COLORS["background"],
            text_color="white",
            border_color=COLORS["accent"],
        )
        self._speak_entry.grid(row=1, column=0, sticky="ew", padx=(20, 5), pady=(0, 15))
        self._speak_entry.bind("<Return>", lambda e: self._do_speak())

        ctk.CTkButton(
            frame,
            text="Say",
            width=80,
            height=32,
            font=("Segoe UI", 13),
            fg_color=COLORS["accent"],
            text_color=COLORS["background"],
            hover_color="#00B8E6",
            command=self._do_speak,
        ).grid(row=1, column=1, padx=(5, 20), pady=(0, 15))

    # ==================================================================
    # Activity log (right column)
    # ==================================================================

    def _build_activity_log(self) -> None:
        log_frame = ctk.CTkFrame(
            self,
            corner_radius=15,
            fg_color=COLORS["card"],
        )
        log_frame.grid(row=0, column=1, rowspan=3, sticky="nsew", padx=(10, 40), pady=30)
        log_frame.grid_rowconfigure(1, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            log_frame,
            text="Recent Voice Activity",
            font=("Segoe UI", 16, "bold"),
            text_color="white",
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(20, 10))

        self._activity_scroll = ctk.CTkScrollableFrame(
            log_frame,
            fg_color="transparent",
        )
        self._activity_scroll.grid(
            row=1, column=0, sticky="nsew", padx=10, pady=(0, 10),
        )
        self._activity_scroll.grid_columnconfigure(0, weight=1)

        self._activity_labels: list[ctk.CTkLabel] = []

    # ==================================================================
    # Lifecycle
    # ==================================================================

    def on_activate(self) -> None:
        bus = self.registry.get("event_bus")
        self._ctrl.subscribe_events(bus)
        self._refresh_status()
        self._timer_id = self.after(2000, self._poll_status)

    def on_deactivate(self) -> None:
        self._ctrl.unsubscribe_events()
        if self._timer_id is not None:
            self.after_cancel(self._timer_id)
            self._timer_id = None

    # ==================================================================
    # Polling
    # ==================================================================

    def _poll_status(self) -> None:
        self._refresh_status()
        self._timer_id = self.after(2000, self._poll_status)

    def _refresh_status(self) -> None:
        running = self._ctrl.is_running()
        self._update_status_ui(running)

    # ==================================================================
    # UI updates
    # ==================================================================

    def _update_status_ui(self, running: bool) -> None:
        colour = COLORS["success"] if running else COLORS["danger"]
        self._status_label.configure(
            text=f"Status: {'Running' if running else 'Stopped'}",
            text_color=colour,
        )
        self._toggle_btn.configure(
            text="Stop" if running else "Start",
            fg_color=COLORS["danger"] if running else COLORS["success"],
            hover_color="#DC2626" if running else "#1DA44E",
        )
        cfg = self._ctrl.config
        ww = cfg.wake_word if cfg.wake_word_enabled else "disabled"
        self._wake_label.configure(text=f"Wake Word: {ww}")

    def _append_live(self, prefix: str, text: str, colour: str = COLORS["text"]) -> None:
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self._live_text.configure(state="normal")
        self._live_text.insert("end", f"[{ts}] {prefix}{text}\n", "colored")
        self._live_text.tag_config("colored", foreground=colour)
        self._live_text.see("end")
        self._live_text.configure(state="disabled")

    def _add_activity(self, prefix: str, text: str, colour: str = COLORS["text"]) -> None:
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        max_len = 100
        display = text if len(text) <= max_len else text[: max_len - 3] + "..."
        lbl = ctk.CTkLabel(
            self._activity_scroll,
            text=f"[{ts}] {prefix}{display}",
            font=("Segoe UI", 12),
            text_color=colour,
            anchor="w",
            wraplength=220,
        )
        lbl.pack(fill="x", padx=5, pady=1)
        self._activity_labels.append(lbl)

        # Keep last 50 entries
        while len(self._activity_labels) > 50:
            old = self._activity_labels.pop(0)
            old.destroy()

    # ==================================================================
    # Callbacks from controller
    # ==================================================================

    def _on_transcript_cb(self, text: str) -> None:
        self._append_live("You: ", text, COLORS["accent"])
        self._add_activity("You said: ", text, COLORS["accent"])

    def _on_response_cb(self, text: str) -> None:
        display = text[:200] + "..." if len(text) > 200 else text
        self._append_live("Assistant: ", display, COLORS["success"])
        self._add_activity("Assistant: ", display, COLORS["success"])

    def _on_error_cb(self, error: str) -> None:
        self._append_live("Error: ", error, COLORS["danger"])
        self._add_activity("Error: ", error, COLORS["danger"])

    def _on_wake_cb(self) -> None:
        self._append_live("", "Wake word detected", COLORS["warning"])
        self._add_activity("", "Wake word detected", COLORS["warning"])

    def _on_running_changed_cb(self, running: bool) -> None:
        self._update_status_ui(running)

    # ==================================================================
    # Actions
    # ==================================================================

    def _toggle_running(self) -> None:
        self._ctrl.toggle_running()

    def _do_speak(self) -> None:
        text = self._speak_entry.get().strip()
        if not text:
            return
        self._ctrl.speak(text)
        self._add_activity("TTS: ", text, COLORS["accent"])
        self._speak_entry.delete(0, "end")
