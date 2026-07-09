from __future__ import annotations

from app.events import event_bus
from app.services import registry


class JarvisKernel:
    """
    Main application kernel.
    Responsible for booting and shutting down JARVIS.
    """

    VERSION = "0.2.0-alpha"

    def __init__(self) -> None:
        self.registry = registry
        self.event_bus = event_bus
        self.running = False

    def boot(self) -> None:
        print("=" * 50)
        print("Starting JARVIS OS...")
        print(f"Version : {self.VERSION}")
        print("=" * 50)

        self.running = True

        print("[OK] Service Registry")
        print("[OK] Event Bus")
        print("[OK] Kernel Ready")

    def shutdown(self) -> None:
        print("\nShutting down JARVIS...")

        self.running = False

        print("[OK] Shutdown Complete")
        