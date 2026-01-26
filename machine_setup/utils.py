"""Utility functions for command execution and logging."""

import logging
import os
import re
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

import click

SECTION_PATTERN = re.compile(r"^=== .* ===$")

logger = logging.getLogger("machine_setup")


class ColorFormatter(logging.Formatter):
    """Custom formatter with color-coded log levels and section headers."""

    LEVEL_COLORS = {
        logging.DEBUG: dict(fg="bright_black"),
        logging.INFO: dict(fg="green"),
        logging.WARNING: dict(fg="yellow"),
        logging.ERROR: dict(fg="red"),
        logging.CRITICAL: dict(fg="red", bold=True),
    }

    def format(self, record: logging.LogRecord) -> str:
        log_level_color = self.LEVEL_COLORS.get(record.levelno, {})
        log_level = click.style(f"{record.levelname:s}:", **log_level_color)

        timestamp = self.formatTime(record, "%H:%M:%S")
        message = record.getMessage()

        if SECTION_PATTERN.match(message.strip()):
            message = click.style(message, bold=True)
            formatted = f"\n[{timestamp}] {log_level} {message}"
        else:
            formatted = f"[{timestamp}] {log_level} {message}"

        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            if formatted[-1] != "\n":
                formatted = f"{formatted}\n"
            formatted = f"{formatted}{record.exc_text}"
        if record.stack_info:
            if formatted[-1] != "\n":
                formatted = f"{formatted}\n"
            formatted = f"{formatted}{self.formatStack(record.stack_info)}"

        return formatted


def setup_logging(verbose: bool = False) -> None:
    """Configure logging with color support."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    root_logger = logging.getLogger()
    root_logger.handlers[0].setFormatter(ColorFormatter())


def run(
    cmd: Sequence[str],
    *,
    check: bool = True,
    capture: bool = False,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a command with logging."""
    logger.debug("Running: %s", " ".join(cmd))
    return subprocess.run(
        cmd,
        check=check,
        capture_output=capture,
        text=True,
        env=env,
    )


def command_exists(cmd: str) -> bool:
    """Check if a command exists in PATH."""
    return shutil.which(cmd) is not None


def sudo_prefix() -> list[str]:
    """Return sudo prefix when not running as root."""
    return [] if os.geteuid() == 0 else ["sudo"]


def path_exists(path: str | Path) -> bool:
    """Check if a path exists (expand ~)."""
    return Path(path).expanduser().exists()


def ensure_dir(path: str | Path) -> Path:
    """Ensure directory exists."""
    p = Path(path).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p
