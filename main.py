from __future__ import annotations

import sys


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("build", "interactive", "status", "--cli"):
        from app.cli import main as cli_main

        if sys.argv[1] == "--cli":
            sys.argv = [sys.argv[0]] + sys.argv[2:]
        cli_main()
    else:
        from app.core.app import JarvisApp
        from app.core.kernel import JarvisKernel

        kernel = JarvisKernel()
        kernel.boot()

        app = JarvisApp(kernel.registry)
        app.run()


if __name__ == "__main__":
    main()
