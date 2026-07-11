from __future__ import annotations

import logging
from pathlib import Path


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
    def info(cls, message: str):

        cls.setup()
        logging.info(message)

    @classmethod
    def warning(cls, message: str):

        cls.setup()
        logging.warning(message)

    @classmethod
    def error(cls, message: str):

        cls.setup()
        logging.error(message)

    @classmethod
    def debug(cls, message: str):

        cls.setup()
        logging.debug(message)