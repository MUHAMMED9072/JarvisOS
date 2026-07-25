from __future__ import annotations

import customtkinter as ctk

from app.core.registry import ServiceRegistry
from app.gui.controllers.settings_controller import SettingsController
from app.gui.pages.base_page import BasePage
from app.gui.theme import COLORS

_TABS = ["General", "AI", "Voice", "Appearance", "System"]


class SettingsPage(BasePage):
    """Settings page with tabbed configuration interface."""

    name = "settings"
    title = "Settings"

    def __init__(self, master, registry: ServiceRegistry) -> None:
        super().__init__(master, registry)

        self._ctrl = SettingsController(registry)
        self._ctrl.on_settings_applied = self._on_settings_applied

        self._tab = "General"

        self._build_top_bar()
        self._build_tab_bar()
        self._build_content_area()
        self._build_save_bar()

    # ==================================================================
    # Top bar
    # ==================================================================

    def _build_top_bar(self) -> None:
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=40, pady=(20, 5))

        ctk.CTkLabel(
            top,
            text="Settings",
            font=("Segoe UI", 24, "bold"),
            text_color="white",
        ).pack(side="left")

    # ==================================================================
    # Tab bar
    # ==================================================================

    def _build_tab_bar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=40, pady=(10, 0))

        self._tab_btns: dict[str, ctk.CTkButton] = {}
        for i, name in enumerate(_TABS):
            active = name == self._tab
            btn = ctk.CTkButton(
                bar,
                text=name,
                width=90,
                height=30,
                font=("Segoe UI", 13),
                fg_color=COLORS["accent"] if active else COLORS["card"],
                text_color=COLORS["background"] if active else COLORS["text"],
                hover_color=COLORS["accent"],
                command=lambda v=name: self._switch_tab(v),
            )
            btn.pack(side="left", padx=(0, 8))
            self._tab_btns[name] = btn

    # ==================================================================
    # Content area
    # ==================================================================

    def _build_content_area(self) -> None:
        self._content = ctk.CTkFrame(
            self,
            corner_radius=15,
            fg_color=COLORS["card"],
        )
        self._content.pack(fill="both", expand=True, padx=40, pady=15)

    # ==================================================================
    # Save bar
    # ==================================================================

    def _build_save_bar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=40, pady=(0, 20))

        self._save_btn = ctk.CTkButton(
            bar,
            text="Save",
            width=80,
            height=32,
            font=("Segoe UI", 13, "bold"),
            fg_color=COLORS["accent"],
            text_color=COLORS["background"],
            hover_color="#00B8E6",
            command=self._save,
        )
        self._save_btn.pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            bar,
            text="Restore Defaults",
            width=120,
            height=32,
            font=("Segoe UI", 13),
            fg_color=COLORS["card"],
            text_color=COLORS["text"],
            hover_color=COLORS["danger"],
            border_width=1,
            border_color=COLORS["danger"],
            command=self._restore_defaults,
        ).pack(side="left")

        self._dirty_label = ctk.CTkLabel(
            bar,
            text="",
            font=("Segoe UI", 12),
            text_color=COLORS["warning"],
            anchor="w",
        )
        self._dirty_label.pack(side="left", padx=(15, 0))

    # ==================================================================
    # Lifecycle
    # ==================================================================

    def on_activate(self) -> None:
        self._render_tab()

    def on_deactivate(self) -> None:
        pass

    # ==================================================================
    # Tab switching
    # ==================================================================

    def _switch_tab(self, name: str) -> None:
        self._tab = name
        for n, btn in self._tab_btns.items():
            active = n == name
            btn.configure(
                fg_color=COLORS["accent"] if active else COLORS["card"],
                text_color=COLORS["background"] if active else COLORS["text"],
            )
        self._render_tab()

    # ==================================================================
    # Render current tab
    # ==================================================================

    def _render_tab(self) -> None:
        for child in self._content.winfo_children():
            child.destroy()

        method = getattr(self, f"_render_{self._tab.lower()}", None)
        if method:
            method()

        self._update_dirty()

    def _render_general(self) -> None:
        self._render_label("General Settings", 16, bold=True, pady=(15, 10))

        # AI Provider
        self._render_label("Default AI Provider", 13)
        providers = self._ctrl.get_available_providers()
        names = [p.name for p in providers]
        current = self._ctrl.get("ai_provider", "ollama")
        if current not in names and names:
            current = names[0]
        self._ai_prov_cb = self._render_combo(names, current, lambda v: self._ctrl.set("ai_provider", v))

        # Log level
        self._render_label("Log Level", 13, pady=(10, 2))
        levels = self._ctrl.get_log_levels()
        current_lvl = self._ctrl.get("log_level", "INFO")
        self._log_lvl_cb = self._render_combo(levels, current_lvl, lambda v: self._ctrl.set("log_level", v))

        self._content.grid_columnconfigure(1, weight=1)

    def _render_ai(self) -> None:
        self._render_label("AI Providers", 16, bold=True, pady=(15, 10))

        providers = self._ctrl.get_available_providers()
        if not providers:
            self._render_label("No AI providers available.", 13)
            return

        for i, p in enumerate(providers):
            colour = COLORS["success"] if p.status == "available" else COLORS["warning"]
            card = ctk.CTkFrame(self._content, fg_color=COLORS["background"], corner_radius=8)
            card.grid(row=i + 1, column=0, columnspan=2, sticky="ew", padx=15, pady=3)
            card.grid_columnconfigure(1, weight=1)

            ctk.CTkLabel(
                card,
                text=f"\u25CF  {p.name}",
                font=("Consolas", 14),
                text_color=colour,
                anchor="w",
            ).grid(row=0, column=0, padx=(12, 8), pady=8, sticky="w")

            ctk.CTkLabel(
                card,
                text=p.status.title(),
                font=("Segoe UI", 12),
                text_color=colour,
                anchor="e",
            ).grid(row=0, column=1, padx=(0, 12), sticky="e")

        self._content.grid_columnconfigure(0, weight=1)

    def _render_voice(self) -> None:
        self._render_label("Voice Settings", 16, bold=True, pady=(15, 10))

        # Enable / Disable
        enabled = self._ctrl.get("voice_enabled", False)
        self._voice_en_var = ctk.BooleanVar(value=enabled)
        ctk.CTkSwitch(
            self._content,
            text="Enable Voice",
            font=("Segoe UI", 13),
            variable=self._voice_en_var,
            command=lambda: self._ctrl.set("voice_enabled", self._voice_en_var.get()),
            progress_color=COLORS["accent"],
        ).grid(row=1, column=0, sticky="w", padx=20, pady=5)

        # Whisper model
        self._render_label("Whisper Model", 13, pady=(10, 2))
        models = self._ctrl.get_whisper_models()
        current_model = self._ctrl.get("whisper_model", "base")
        self._whisper_cb = self._render_combo(models, current_model, lambda v: self._ctrl.set("whisper_model", v))

        # Wake word
        ww = self._ctrl.get("wake_word_enabled", False)
        self._ww_var = ctk.BooleanVar(value=ww)
        ctk.CTkSwitch(
            self._content,
            text="Wake Word Detection",
            font=("Segoe UI", 13),
            variable=self._ww_var,
            command=lambda: self._ctrl.set("wake_word_enabled", self._ww_var.get()),
            progress_color=COLORS["accent"],
        ).grid(row=3, column=0, sticky="w", padx=20, pady=10)

        self._content.grid_columnconfigure(0, weight=1)

    def _render_appearance(self) -> None:
        self._render_label("Appearance", 16, bold=True, pady=(15, 10))

        # Theme
        self._render_label("Theme Mode", 13)
        modes = self._ctrl.get_theme_modes()
        current_theme = self._ctrl.get("theme_mode", "dark")
        self._theme_cb = self._render_combo(modes, current_theme, lambda v: self._ctrl.set("theme_mode", v))

        self._content.grid_columnconfigure(1, weight=1)

    def _render_system(self) -> None:
        self._render_label("System Information", 16, bold=True, pady=(15, 10))

        info = [
            ("Version", self._ctrl.get_version()),
            ("Data Directory", str(Config.DATA_DIR)),
            ("Log Directory", str(Config.LOG_DIR)),
            ("Configuration", str(Config.ROOT / "data" / "settings.json")),
        ]
        try:
            from app.core.config import Config
            info.append(("Application", Config.APP_NAME))
        except Exception:
            pass

        for i, (label, value) in enumerate(info):
            row = i + 1
            ctk.CTkLabel(
                self._content,
                text=label,
                font=("Segoe UI", 13, "bold"),
                text_color="white",
                anchor="w",
            ).grid(row=row, column=0, sticky="w", padx=20, pady=4)

            ctk.CTkLabel(
                self._content,
                text=str(value),
                font=("Consolas", 12),
                text_color=COLORS["text"],
                anchor="w",
            ).grid(row=row, column=1, sticky="w", padx=20, pady=4)

        self._content.grid_columnconfigure(1, weight=1)

    # ==================================================================
    # Helpers
    # ==================================================================

    def _render_label(self, text: str, font_size: int, *, bold: bool = False, pady: tuple = (5, 2)) -> None:
        font_weight = "bold" if bold else "normal"
        ctk.CTkLabel(
            self._content,
            text=text,
            font=("Segoe UI", font_size, font_weight),
            text_color="white",
            anchor="w",
        ).grid(sticky="w", padx=20, pady=pady)

    def _render_combo(self, values: list[str], default: str, command) -> ctk.CTkOptionMenu:
        cb = ctk.CTkOptionMenu(
            self._content,
            values=values,
            font=("Segoe UI", 13),
            fg_color=COLORS["background"],
            button_color=COLORS["accent"],
            button_hover_color="#00B8E6",
            text_color="white",
            command=command,
        )
        cb.set(default if default in values else (values[0] if values else ""))
        cb.grid(sticky="w", padx=20, pady=2)
        return cb

    # ==================================================================
    # Dirty state
    # ==================================================================

    def _update_dirty(self) -> None:
        if self._ctrl.has_unsaved_changes:
            self._dirty_label.configure(text="Unsaved changes")
            self._save_btn.configure(
                fg_color=COLORS["warning"],
                text_color=COLORS["background"],
            )
        else:
            self._dirty_label.configure(text="")
            self._save_btn.configure(
                fg_color=COLORS["accent"],
                text_color=COLORS["background"],
            )

    # ==================================================================
    # Actions
    # ==================================================================

    def _save(self) -> None:
        self._ctrl.save()
        self._update_dirty()

    def _restore_defaults(self) -> None:
        self._ctrl.restore_defaults()
        self._render_tab()
        # Re-apply theme immediately
        self._ctrl.apply()

    def _on_settings_applied(self, settings: dict) -> None:
        theme = settings.get("theme_mode", "dark")
        ctk.set_appearance_mode(theme)
