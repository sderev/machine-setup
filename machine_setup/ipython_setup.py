"""IPython math profile setup with uv-managed virtual environment."""

import logging
import subprocess
from pathlib import Path
from textwrap import dedent

from machine_setup.utils import command_exists

logger = logging.getLogger("machine_setup")

IPYTHON_MATH_DIR = Path.home() / ".local/share/ipython-math"
IPYTHON_MATH_BIN = Path.home() / ".local/bin/ipython-math"

PYPROJECT_TOML = dedent("""\
    [project]
    name = "ipython-math"
    version = "1.0.0"
    requires-python = ">=3.10"
    dependencies = [
        "ipython>=8.0",
        "numpy>=1.20",
        "pandas>=1.3",
        "matplotlib>=3.5",
        "scipy>=1.10",
        "sympy>=1.12",
        "scikit-learn>=1.0",
        "seaborn>=0.12",
    ]
""")

WRAPPER_SCRIPT = dedent("""\
    #!/bin/bash
    cd "$HOME/.local/share/ipython-math"
    exec uv run ipython --profile=math "$@"
""")


def setup_ipython_math_profile() -> None:
    """Set up IPython math profile with uv-managed virtual environment."""
    if not command_exists("uv"):
        logger.warning("uv not found; skipping ipython math profile setup")
        return

    logger.info("Setting up IPython math profile...")

    IPYTHON_MATH_DIR.mkdir(parents=True, exist_ok=True)

    pyproject_path = IPYTHON_MATH_DIR / "pyproject.toml"
    if not pyproject_path.exists():
        pyproject_path.write_text(PYPROJECT_TOML)
        logger.info("Created %s", pyproject_path)

    logger.info("Installing math packages with uv...")
    result = subprocess.run(
        ["uv", "sync"],
        cwd=IPYTHON_MATH_DIR,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.warning("Failed to sync ipython-math environment: %s", result.stderr)
        return

    IPYTHON_MATH_BIN.parent.mkdir(parents=True, exist_ok=True)
    IPYTHON_MATH_BIN.write_text(WRAPPER_SCRIPT)
    IPYTHON_MATH_BIN.chmod(0o755)
    logger.info("Created wrapper script %s", IPYTHON_MATH_BIN)

    logger.info("IPython math profile setup complete")
    logger.info("Use 'ipython-math' to start IPython with math packages")
