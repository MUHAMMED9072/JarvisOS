from __future__ import annotations

import customtkinter as ctk

from app.core.registry import ServiceRegistry
from app.gui.controllers.skills_controller import SkillsController
from app.gui.pages.base_page import BasePage
from app.gui.theme import COLORS


class SkillsPage(BasePage):
    """Skills Manager: list, search, toggle, reload skills."""

    name = "skills"
    title = "Skills"

    def __init__(self, master, registry: ServiceRegistry) -> None:
        super().__init__(master, registry)

        self._ctrl = SkillsController(registry)

        # Top area (overview + controls)
        self._build_top_bar()
        self._build_controls()

        # Scrollable skill cards
        self._build_card_area()

    # ==================================================================
    # Top bar
    # ==================================================================

    def _build_top_bar(self) -> None:
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=40, pady=(20, 5))

        ctk.CTkLabel(
            top,
            text="Skills Manager",
            font=("Segoe UI", 24, "bold"),
            text_color="white",
        ).pack(side="left")

    # ==================================================================
    # Controls row (stats, search, buttons)
    # ==================================================================

    def _build_controls(self) -> None:
        controls = ctk.CTkFrame(self, fg_color="transparent")
        controls.pack(fill="x", padx=40, pady=(10, 10))
        controls.grid_columnconfigure(2, weight=1)

        self._stats_label = ctk.CTkLabel(
            controls,
            text="Loading...",
            font=("Consolas", 13),
            text_color=COLORS["text"],
            anchor="w",
        )
        self._stats_label.grid(row=0, column=0, padx=(0, 20))

        self._search_entry = ctk.CTkEntry(
            controls,
            placeholder_text="Search skills...",
            font=("Segoe UI", 13),
            width=220,
            fg_color=COLORS["card"],
            text_color="white",
            border_color=COLORS["accent"],
        )
        self._search_entry.grid(row=0, column=1, padx=(0, 10))
        self._search_entry.bind("<Return>", lambda e: self._do_search())

        btn_row = ctk.CTkFrame(controls, fg_color="transparent")
        btn_row.grid(row=0, column=3)

        ctk.CTkButton(
            btn_row,
            text="Reload All",
            width=100,
            height=32,
            font=("Segoe UI", 13),
            fg_color=COLORS["card"],
            text_color=COLORS["text"],
            hover_color=COLORS["accent"],
            border_width=1,
            border_color=COLORS["accent"],
            command=self._reload_all,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row,
            text="Refresh",
            width=90,
            height=32,
            font=("Segoe UI", 13),
            fg_color=COLORS["card"],
            text_color=COLORS["text"],
            hover_color=COLORS["accent"],
            border_width=1,
            border_color=COLORS["accent"],
            command=self._refresh,
        ).pack(side="left")

    # ==================================================================
    # Skill cards area
    # ==================================================================

    def _build_card_area(self) -> None:
        scroll = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
        )
        scroll.pack(fill="both", expand=True, padx=40, pady=(0, 20))
        scroll.grid_columnconfigure(0, weight=1)

        self._card_area = scroll
        self._card_frames: list[ctk.CTkFrame] = []

    # ==================================================================
    # Lifecycle
    # ==================================================================

    def on_activate(self) -> None:
        self._refresh()

    def on_deactivate(self) -> None:
        pass

    # ==================================================================
    # Refresh
    # ==================================================================

    def _refresh(self) -> None:
        self._update_stats()
        self._render_skills()

    def _do_search(self) -> None:
        self._render_skills()

    # ==================================================================
    # Stats
    # ==================================================================

    def _update_stats(self) -> None:
        stats = self._ctrl.get_statistics()
        self._stats_label.configure(
            text=(
                f"Total: {stats.total}  |  "
                f"Enabled: {stats.enabled}  |  "
                f"Disabled: {stats.disabled}"
            )
        )

    # ==================================================================
    # Render skill cards
    # ==================================================================

    def _render_skills(self) -> None:
        for f in self._card_frames:
            f.destroy()
        self._card_frames.clear()

        query = self._search_entry.get().strip()
        skills = self._ctrl.search_skills(query)

        for info in skills:
            self._render_skill_card(info)

    def _render_skill_card(self, info) -> None:
        card = ctk.CTkFrame(
            self._card_area,
            corner_radius=10,
            fg_color=COLORS["card"],
        )
        card.grid(sticky="ew", pady=4)
        card.grid_columnconfigure(1, weight=1)

        # Toggle indicator (coloured dot)
        dot_colour = COLORS["success"] if info.enabled else COLORS["danger"]
        dot = ctk.CTkLabel(
            card,
            text="\u25CF",
            font=("Segoe UI", 18),
            text_color=dot_colour,
        )
        dot.grid(row=0, column=0, rowspan=2, padx=(15, 8), pady=12, sticky="n")

        # Name & intent
        ctk.CTkLabel(
            card,
            text=info.name,
            font=("Segoe UI", 15, "bold"),
            text_color="white",
            anchor="w",
        ).grid(row=0, column=1, sticky="w", padx=(0, 10), pady=(10, 0))

        ctk.CTkLabel(
            card,
            text=f"intent: {info.intent}",
            font=("Consolas", 11),
            text_color=COLORS["accent"],
            anchor="w",
        ).grid(row=1, column=1, sticky="w", padx=(0, 10), pady=(0, 2))

        # Description (2nd row spanning columns 0-1)
        desc = info.description or "No description"
        ctk.CTkLabel(
            card,
            text=desc,
            font=("Segoe UI", 12),
            text_color=COLORS["text"],
            anchor="w",
            wraplength=500,
        ).grid(row=2, column=0, columnspan=2, sticky="w", padx=15, pady=(0, 10))

        # Version & author
        ctk.CTkLabel(
            card,
            text=f"v{info.version}  |  {info.author}",
            font=("Segoe UI", 11),
            text_color="#94A3B8",
            anchor="w",
        ).grid(row=3, column=0, columnspan=2, sticky="w", padx=15, pady=(0, 12))

        # Toggle button
        btn_text = "Disable" if info.enabled else "Enable"
        btn_fg = COLORS["danger"] if info.enabled else COLORS["success"]
        btn = ctk.CTkButton(
            card,
            text=btn_text,
            width=80,
            height=28,
            font=("Segoe UI", 12),
            fg_color=btn_fg,
            text_color="white",
            hover_color="#DC2626" if info.enabled else "#1DA44E",
            command=lambda i=info.intent: self._toggle_skill(i),
        )
        btn.grid(row=0, column=2, rowspan=2, padx=(0, 15), sticky="e")

        self._card_frames.append(card)

    # ==================================================================
    # Actions
    # ==================================================================

    def _toggle_skill(self, intent: str) -> None:
        self._ctrl.toggle_skill(intent)
        self._render_skills()
        self._update_stats()

    def _reload_all(self) -> None:
        self._ctrl.reload_all()
        self._refresh()
