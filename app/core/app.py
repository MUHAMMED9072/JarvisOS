from __future__ import annotations

from app.core.registry import ServiceRegistry
from app.gui.window import JarvisWindow


class JarvisApp:

    def __init__(self, registry: ServiceRegistry):

        self.registry = registry

    def run(self):
        window = JarvisWindow(self.registry)
        window.mainloop()