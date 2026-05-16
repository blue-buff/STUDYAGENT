import logging
import random
import time
import sys
from pathlib import Path

logger = logging.getLogger("jyeoo")


def setup_logging(level: int = logging.INFO, log_file: Path | None = None):
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")
    logger.setLevel(level)
    logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(fmt)
    logger.addHandler(handler)

    if log_file:
        fh = logging.FileHandler(str(log_file), encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)


def random_delay(min_s: float = 2.0, max_s: float = 5.0):
    delay = random.uniform(min_s, max_s)
    logger.debug(f"Sleeping {delay:.1f}s")
    time.sleep(delay)


def safe_filename(text: str) -> str:
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in text)


def truncate_text(text: str, max_len: int = 500) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)
