from __future__ import annotations

import customtkinter as ctk

from app.core.registry import ServiceRegistry

from .components.sidebar import Sidebar
from .components.statusbar import StatusBar
from .components.topbar import TopBar
from .theme import COLORS, APP_TITLE, WINDOW_WIDTH, WINDOW_HEIGHT


class JarvisWindow(ctk.CTk):

    def __init__(self, registry: ServiceRegistry) -> None:
        super().__init__()

        self.registry = registry

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title(APP_TITLE)

        self.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")

        self.minsize(1200, 700)

        self.configure(fg_color=COLORS["background"])

        self.pages: dict[str, ctk.CTkFrame] = {}
        self.current_page: ctk.CTkFrame | None = None

        self.build_sidebar()

        self.build_main()

        self._init_pages()

        self.switch_page("dashboard")

    # =====================================
    # SIDEBAR
    # =====================================

    def build_sidebar(self) -> None:

        self.sidebar = Sidebar(
            self,
            on_navigate=self.switch_page,
        )

        self.sidebar.pack(
            side="left",
            fill="y",
        )

    # =====================================
    # MAIN AREA
    # =====================================

    def build_main(self) -> None:

        self.main = ctk.CTkFrame(
            self,
            fg_color=COLORS["background"],
        )

        self.main.pack(
            side="right",
            fill="both",
            expand=True,
        )

        # Top bar
        self.topbar = TopBar(self.main)
        self.topbar.pack(
            fill="x",
            padx=40,
            pady=(30, 5),
        )

        # Page container — exactly one page visible at a time
        self.page_container = ctk.CTkFrame(
            self.main,
            fg_color="transparent",
        )

        self.page_container.pack(
            fill="both",
            expand=True,
        )

        # Status bar
        self.statusbar = StatusBar(self.main, self.registry)
        self.statusbar.pack(
            fill="x",
            side="bottom",
        )

    # =====================================
    # PAGE REGISTRATION
    # =====================================

    def _init_pages(self) -> None:

        from app.gui.pages.dashboard import DashboardPage
        from app.gui.pages.ai_chat import AIChatPage
        from app.gui.pages.voice import VoicePage
        from app.gui.pages.memory import MemoryPage
        from app.gui.pages.skills import SkillsPage
        from app.gui.pages.ai import AIPage
        from app.gui.pages.settings import SettingsPage
        from app.gui.pages.logs import LogsPage

        page_classes = [
            DashboardPage,
            AIChatPage,
            VoicePage,
            MemoryPage,
            SkillsPage,
            AIPage,
            SettingsPage,
            LogsPage,
        ]

        for cls in page_classes:
            page = cls(self.page_container, self.registry)
            self.pages[page.name] = page

    # =====================================
    # NAVIGATION
    # =====================================

    def switch_page(self, page_name: str) -> None:

        if self.current_page is not None:
            self.current_page.on_deactivate()
            self.current_page.pack_forget()

        page = self.pages.get(page_name)

        if page is None:
            return

        self.current_page = page
        page.pack(fill="both", expand=True)
        page.on_activate()

        self.topbar.set_title(page.title)
        self.sidebar.set_active(page_name)
        self.statusbar.set_status(f"Page: {page.title}")
