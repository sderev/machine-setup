"""Claude Code CLI installation."""

import logging
import subprocess

from machine_setup.utils import command_exists

logger = logging.getLogger("machine_setup")

INSTALL_URL = "https://claude.ai/install.sh"


def install_claude_code() -> None:
    """Install Claude Code CLI via native binary installer."""
    if command_exists("claude"):
        logger.info("Claude Code already installed")
        return

    logger.info("Installing Claude Code CLI...")

    try:
        # Fetch and run the installer
        curl = subprocess.run(
            ["curl", "-fsSL", "--max-time", "30", INSTALL_URL],
            capture_output=True,
            text=True,
            check=True,
        )

        subprocess.run(
            ["bash"],
            input=curl.stdout,
            check=True,
        )

        logger.info("Claude Code installed successfully")
        logger.info(
            "You may need to restart your shell or run `source ~/.bashrc` "
            "for the `claude` command to be available"
        )
    except subprocess.CalledProcessError as error:
        logger.warning("Failed to install Claude Code: %s", error)
