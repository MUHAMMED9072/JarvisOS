import customtkinter as ctk

from .theme import *
from app.core.registry import ServiceRegistry
from app.utils.system import *


class JarvisWindow(ctk.CTk):

    def __init__(self, registry: ServiceRegistry):
        super().__init__()

        self.registry = registry

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title(APP_TITLE)

        self.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")

        self.minsize(1200, 700)

        self.configure(
            fg_color=COLORS["background"]
        )

        self.build_sidebar()

        self.build_main()

        self.update_dashboard()

    # =====================================
    # SIDEBAR
    # =====================================

    def build_sidebar(self):

        self.sidebar = ctk.CTkFrame(
            self,
            width=240,
            corner_radius=0,
            fg_color=COLORS["sidebar"]
        )

        self.sidebar.pack(
            side="left",
            fill="y"
        )

        self.logo = ctk.CTkLabel(
            self.sidebar,
            text="🤖 JARVIS",
            font=("Segoe UI", 30, "bold"),
            text_color=COLORS["accent"]
        )

        self.logo.pack(
            pady=(35, 25)
        )

        menu = [
            "🏠 Dashboard",
            "💬 Chat",
            "🎤 Voice",
            "🧠 Memory",
            "⚡ Skills",
            "🤖 AI",
            "⚙ Settings",
            "📜 Logs"
        ]

        for item in menu:

            button = ctk.CTkButton(
                self.sidebar,
                text=item,
                anchor="w",
                height=42,
                corner_radius=8
            )

            button.pack(
                fill="x",
                padx=15,
                pady=5
            )

    # =====================================
    # MAIN AREA
    # =====================================

    def build_main(self):

        self.main = ctk.CTkFrame(
            self,
            fg_color=COLORS["background"]
        )

        self.main.pack(
            side="right",
            fill="both",
            expand=True
        )

        self.header()

        self.dashboard()

    # =====================================
    # HEADER
    # =====================================

    def header(self):

        title = ctk.CTkLabel(
            self.main,
            text="Welcome to JARVIS OS",
            font=("Segoe UI", 32, "bold"),
            text_color="white"
        )

        title.pack(
            anchor="nw",
            padx=40,
            pady=(30, 5)
        )

        subtitle = ctk.CTkLabel(
            self.main,
            text="Your personal AI operating system",
            font=("Segoe UI", 16),
            text_color="#94A3B8"
        )

        subtitle.pack(
            anchor="nw",
            padx=40
        )

    # =====================================
    # DASHBOARD
    # =====================================

    def dashboard(self):

        self.card = ctk.CTkFrame(
            self.main,
            width=900,
            height=320,
            corner_radius=15,
            fg_color=COLORS["card"]
        )

        self.card.pack(
            anchor="nw",
            padx=40,
            pady=30
        )

        self.card.pack_propagate(False)

        title = ctk.CTkLabel(
            self.card,
            text="System Monitor",
            font=("Segoe UI",24,"bold"),
            text_color="white"
        )

        title.pack(
            anchor="nw",
            padx=20,
            pady=(20,10)
        )

        self.status = ctk.CTkLabel(
            self.card,
            justify="left",
            font=("Consolas",17),
            text_color="white"
        )

        self.status.pack(
            anchor="nw",
            padx=20
        )
    # =====================================
    # LIVE DASHBOARD
    # =====================================

    def update_dashboard(self):

        try:

            cpu = cpu_usage()
            ram = ram_usage()
            disk = disk_usage()
            internet = internet_status()
            os_name = operating_system()
            py = python_version()
            clock = current_time()

            self.status.configure(
               text=(
    f"CPU Usage      : {cpu}\n\n"
    f"RAM Usage      : {ram}\n\n"
    f"Disk Usage     : {disk}\n\n"
    f"Internet       : {internet}\n\n"
    f"Operating Sys  : {os_name}\n\n"
    f"Python Version : {py}\n\n"
    f"Time           : {clock}\n\n"
    f"Ollama Status  : Online\n\n"
    f"Voice Engine   : Ready"
)
            )

        except Exception as e:

            self.status.configure(
                text=f"Dashboard Error:\n\n{e}"
            )

        self.after(
            1000,
            self.update_dashboard
        )