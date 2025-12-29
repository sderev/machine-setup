"""Utility functions for command execution and logging."""

import logging
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

logger = logging.getLogger("machine_setup")


def setup_logging(verbose: bool = False) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )


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


def path_exists(path: str | Path) -> bool:
    """Check if a path exists (expand ~)."""
    return Path(path).expanduser().exists()


def ensure_dir(path: str | Path) -> Path:
    """Ensure directory exists."""
    p = Path(path).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p
