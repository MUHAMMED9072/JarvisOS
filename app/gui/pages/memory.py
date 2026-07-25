from __future__ import annotations

import customtkinter as ctk

from app.core.registry import ServiceRegistry
from app.gui.controllers.memory_controller import MemoryController, SearchResult
from app.gui.pages.base_page import BasePage
from app.gui.theme import COLORS
from app.gui.widgets.message_bubble import MessageBubble


class MemoryPage(BasePage):
    """Memory Center: session history, search, stats, preferences."""

    name = "memory"
    title = "Memory"

    def __init__(self, master, registry: ServiceRegistry) -> None:
        super().__init__(master, registry)

        self._ctrl = MemoryController(registry)

        self.grid_columnconfigure(0, weight=3, minsize=450)
        self.grid_columnconfigure(1, weight=2, minsize=320)

        self._build_conversation_panel()
        self._build_side_panel()

    # ==================================================================
    # Left column — session conversation
    # ==================================================================

    def _build_conversation_panel(self) -> None:
        panel = ctk.CTkFrame(
            self,
            corner_radius=15,
            fg_color=COLORS["card"],
        )
        panel.grid(row=0, column=0, sticky="nsew", padx=(40, 10), pady=30)
        panel.grid_rowconfigure(1, weight=1)
        panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            panel,
            text="Session Conversation",
            font=("Segoe UI", 20, "bold"),
            text_color="white",
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(20, 10))

        self._scroll = ctk.CTkScrollableFrame(
            panel,
            fg_color="transparent",
        )
        self._scroll.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self._scroll.grid_columnconfigure(0, weight=1)

        self._bubble_rows: list[ctk.CTkFrame] = []

        btn_row = ctk.CTkFrame(panel, fg_color="transparent")
        btn_row.grid(row=2, column=0, sticky="ew", padx=15, pady=(0, 15))
        btn_row.grid_columnconfigure(2, weight=1)

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
        ).grid(row=0, column=0, padx=(0, 8))

        ctk.CTkButton(
            btn_row,
            text="Clear Session",
            width=110,
            height=32,
            font=("Segoe UI", 13),
            fg_color=COLORS["danger"],
            text_color="white",
            hover_color="#DC2626",
            command=self._clear_session,
        ).grid(row=0, column=1)

    # ==================================================================
    # Right column — stats, search, context, preferences
    # ==================================================================

    def _build_side_panel(self) -> None:
        panel = ctk.CTkFrame(
            self,
            corner_radius=15,
            fg_color=COLORS["card"],
        )
        panel.grid(row=0, column=1, sticky="nsew", padx=(10, 40), pady=30)
        panel.grid_rowconfigure(6, weight=1)
        panel.grid_columnconfigure(0, weight=1)

        # -- Stats --
        ctk.CTkLabel(
            panel,
            text="Memory Overview",
            font=("Segoe UI", 20, "bold"),
            text_color="white",
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(20, 10))

        self._stats_label = ctk.CTkLabel(
            panel,
            text="Loading...",
            font=("Consolas", 13),
            text_color=COLORS["text"],
            anchor="w",
            justify="left",
        )
        self._stats_label.grid(row=1, column=0, sticky="w", padx=20, pady=(0, 12))

        # -- Search --
        ctk.CTkLabel(
            panel,
            text="Search Memories",
            font=("Segoe UI", 16, "bold"),
            text_color="white",
            anchor="w",
        ).grid(row=2, column=0, sticky="w", padx=20, pady=(0, 5))

        search_row = ctk.CTkFrame(panel, fg_color="transparent")
        search_row.grid(row=3, column=0, sticky="ew", padx=15, pady=(0, 5))
        search_row.grid_columnconfigure(0, weight=1)

        self._search_entry = ctk.CTkEntry(
            search_row,
            placeholder_text="Search...",
            font=("Segoe UI", 13),
            fg_color=COLORS["background"],
            text_color="white",
            border_color=COLORS["accent"],
        )
        self._search_entry.grid(row=0, column=0, sticky="ew", padx=(5, 5))
        self._search_entry.bind("<Return>", lambda e: self._do_search())

        ctk.CTkButton(
            search_row,
            text="Find",
            width=60,
            height=30,
            font=("Segoe UI", 12),
            fg_color=COLORS["accent"],
            text_color=COLORS["background"],
            hover_color="#00B8E6",
            command=self._do_search,
        ).grid(row=0, column=1, padx=(0, 5))

        self._search_results = ctk.CTkScrollableFrame(
            panel,
            fg_color="transparent",
            height=120,
        )
        self._search_results.grid(row=4, column=0, sticky="nsew", padx=10, pady=(0, 8))
        self._search_results.grid_columnconfigure(0, weight=1)

        # -- Context --
        ctk.CTkLabel(
            panel,
            text="Current Context",
            font=("Segoe UI", 16, "bold"),
            text_color="white",
            anchor="w",
        ).grid(row=5, column=0, sticky="w", padx=20, pady=(10, 5))

        self._context_label = ctk.CTkLabel(
            panel,
            text="",
            font=("Consolas", 12),
            text_color=COLORS["text"],
            anchor="w",
            justify="left",
        )
        self._context_label.grid(row=6, column=0, sticky="wn", padx=20, pady=(0, 5))

        # -- Preferences --
        ctk.CTkLabel(
            panel,
            text="Stored Preferences",
            font=("Segoe UI", 16, "bold"),
            text_color="white",
            anchor="w",
        ).grid(row=7, column=0, sticky="w", padx=20, pady=(10, 5))

        self._prefs_label = ctk.CTkLabel(
            panel,
            text="",
            font=("Consolas", 12),
            text_color=COLORS["text"],
            anchor="w",
            justify="left",
        )
        self._prefs_label.grid(row=8, column=0, sticky="wn", padx=20, pady=(0, 20))

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
        self._load_conversation()
        self._update_stats()
        self._update_context()
        self._update_preferences()

    # ==================================================================
    # Conversation
    # ==================================================================

    def _load_conversation(self) -> None:
        for row in self._bubble_rows:
            row.destroy()
        self._bubble_rows.clear()

        messages = self._ctrl.get_session_messages()
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if content:
                self._add_bubble(content, role)

    def _add_bubble(self, text: str, role: str) -> None:
        row = ctk.CTkFrame(self._scroll, fg_color="transparent")
        row.grid(sticky="ew", pady=(2, 2))
        row.grid_columnconfigure(0, weight=1)

        bubble = MessageBubble(row, text, role)
        bubble.pack(fill="x")
        self._bubble_rows.append(row)

    # ==================================================================
    # Stats
    # ==================================================================

    def _update_stats(self) -> None:
        stats = self._ctrl.get_statistics()
        self._stats_label.configure(
            text=(
                f"Total memories   : {stats.total_items}\n"
                f"Session messages : {stats.session_messages}\n"
                f"Last application : {stats.last_application or '--'}"
            )
        )

    # ==================================================================
    # Context
    # ==================================================================

    def _update_context(self) -> None:
        ctx = self._ctrl.get_session_context()
        intent = ctx.get("intent", "")
        entities = ctx.get("entities", {})
        skill = ctx.get("skill", "")
        parts = []
        if intent:
            parts.append(f"Intent   : {intent}")
        if entities:
            parts.append(f"Entities : {entities}")
        if skill:
            parts.append(f"Skill    : {skill}")
        self._context_label.configure(text="\n".join(parts) if parts else "No active context")

    # ==================================================================
    # Preferences
    # ==================================================================

    def _update_preferences(self) -> None:
        prefs = self._ctrl.get_preferences()
        if prefs:
            text = "\n".join(f"  {k}: {v}" for k, v in prefs.items())
        else:
            text = "No stored preferences"
        self._prefs_label.configure(text=text)

    # ==================================================================
    # Actions
    # ==================================================================

    def _clear_session(self) -> None:
        self._ctrl.clear_session()
        self._refresh()

    def _do_search(self) -> None:
        query = self._search_entry.get().strip()
        for child in self._search_results.winfo_children():
            child.destroy()
        if not query:
            return
        results = self._ctrl.search_memories(query)
        if not results:
            lbl = ctk.CTkLabel(
                self._search_results,
                text="No results found.",
                font=("Segoe UI", 12),
                text_color=COLORS["text"],
                anchor="w",
            )
            lbl.pack(fill="x", padx=5, pady=2)
            return
        for r in results:
            role_tag = "User" if r.role == "user" else "Assistant"
            preview = r.content[:120] + "..." if len(r.content) > 120 else r.content
            lbl = ctk.CTkLabel(
                self._search_results,
                text=f"[{role_tag}] {preview}",
                font=("Segoe UI", 12),
                text_color=COLORS["text"],
                anchor="w",
                wraplength=280,
            )
            lbl.pack(fill="x", padx=5, pady=2)
