import customtkinter as ctk

from .theme import *


class JarvisWindow(ctk.CTk):

    def __init__(self):
        super().__init__()

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title(APP_TITLE)

        self.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")

        self.configure(
            fg_color=COLORS["background"]
        )

        self.build_ui()

    def build_ui(self):

        # ==========================
        # Sidebar
        # ==========================

        self.sidebar = ctk.CTkFrame(
            self,
            width=SIDEBAR_WIDTH,
            corner_radius=0,
            fg_color=COLORS["sidebar"]
        )

        self.sidebar.pack(
            side="left",
            fill="y"
        )

        # ==========================
        # Main Content
        # ==========================

        self.content = ctk.CTkFrame(
            self,
            fg_color=COLORS["background"]
        )

        self.content.pack(
            side="right",
            fill="both",
            expand=True
        )

        # ==========================
        # Sidebar Title
        # ==========================

        title = ctk.CTkLabel(
            self.sidebar,
            text="🤖 JARVIS",
            font=("Segoe UI", 28, "bold"),
            text_color=COLORS["accent"]
        )

        title.pack(
            pady=(30, 20)
        )

        # ==========================
        # Sidebar Menu
        # ==========================

        menu_items = [
            "🏠 Dashboard",
            "💬 Chat",
            "🎤 Voice",
            "⚡ Skills",
            "🧠 Memory",
            "🤖 AI",
            "⚙ Settings",
            "📜 Logs"
        ]

        for item in menu_items:

            btn = ctk.CTkButton(
                self.sidebar,
                text=item,
                height=45,
                anchor="w",
                corner_radius=8
            )

            btn.pack(
                fill="x",
                padx=15,
                pady=5
            )

        # ==========================
        # Welcome Section
        # ==========================

        header = ctk.CTkLabel(
            self.content,
            text="Welcome to JARVIS OS",
            font=("Segoe UI", 30, "bold"),
            text_color="white"
        )

        header.pack(
            anchor="nw",
            padx=40,
            pady=(35, 10)
        )

        subtitle = ctk.CTkLabel(
            self.content,
            text="Your personal AI operating system",
            font=("Segoe UI", 16),
            text_color="#A0AEC0"
        )

        subtitle.pack(
            anchor="nw",
            padx=40
        )

        # ==========================
        # Dashboard Card
        # ==========================

        dashboard = ctk.CTkFrame(
            self.content,
            width=900,
            height=240,
            corner_radius=15,
            fg_color=COLORS["card"]
        )

        dashboard.pack(
            anchor="nw",
            padx=40,
            pady=30
        )

        dashboard.pack_propagate(False)

        # Dashboard Title

        dashboard_title = ctk.CTkLabel(
            dashboard,
            text="System Status",
            font=("Segoe UI", 22, "bold"),
            text_color="white"
        )

        dashboard_title.pack(
            anchor="nw",
            padx=20,
            pady=(20, 10)
        )

        # Status Information

        status = ctk.CTkLabel(
            dashboard,
            text="""
CPU Usage      : Loading...
RAM Usage      : Loading...
Ollama Status  : Online
Voice Engine   : Ready
Internet       : Connected
Time           : Loading...
""",
            justify="left",
            font=("Consolas", 16),
            text_color=COLORS["text"]
        )

        status.pack(
            anchor="nw",
            padx=20
        )