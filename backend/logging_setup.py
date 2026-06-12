import logging
import os


def setup_logging() -> None:
    """Configure root logging from the LOG_LEVEL env var (default INFO)."""
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = logging.getLevelNamesMapping().get(level_name)
    if level is None:
        raise ValueError(f"Invalid LOG_LEVEL: {level_name!r}")
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )
