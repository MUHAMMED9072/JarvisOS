from __future__ import annotations

import logging
from pathlib import Path
from typing import Any


class JarvisLogger:

    _initialized = False

    @classmethod
    def setup(cls):

        if cls._initialized:
            return

        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)

        log_file = log_dir / "jarvis.log"

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            handlers=[
                logging.FileHandler(log_file, encoding="utf-8"),
                logging.StreamHandler()
            ]
        )

        cls._initialized = True

    @classmethod
    def debug(cls, message: str, *args: Any, **kwargs: Any) -> None:

        cls.setup()
        logging.debug(message, *args, **kwargs)

    @classmethod
    def info(cls, message: str, *args: Any, **kwargs: Any) -> None:

        cls.setup()
        logging.info(message, *args, **kwargs)

    @classmethod
    def warning(cls, message: str, *args: Any, **kwargs: Any) -> None:

        cls.setup()
        logging.warning(message, *args, **kwargs)

    @classmethod
    def error(cls, message: str, *args: Any, **kwargs: Any) -> None:

        cls.setup()
        logging.error(message, *args, **kwargs)

    @classmethod
    def exception(cls, message: str, *args: Any, **kwargs: Any) -> None:

        cls.setup()
        logging.exception(message, *args, **kwargs)