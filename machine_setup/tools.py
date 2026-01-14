"""Tool installation with uv and Claude Code."""

import logging
import subprocess

from machine_setup.utils import command_exists, run

logger = logging.getLogger("machine_setup")

CLAUDE_INSTALL_URL = "https://claude.ai/install.sh"


def install_uv_tools(tools: list[str]) -> None:
    """Install Python tools using uv tool install."""
    if not tools:
        logger.info("No uv tools to install")
        return

    if not command_exists("uv"):
        logger.warning("uv not found; skipping uv tool installation")
        return

    for tool in tools:
        logger.info("Installing %s via uv tool...", tool)
        result = run(["uv", "tool", "install", tool], check=False)
        if result.returncode != 0:
            logger.warning("uv tool install failed for %s", tool)


def install_claude_code() -> None:
    """Install Claude Code CLI via native binary installer."""
    if command_exists("claude"):
        logger.info("Claude Code already installed")
        return

    logger.info("Installing Claude Code CLI...")

    try:
        curl = subprocess.run(
            ["curl", "-fsSL", "--max-time", "30", CLAUDE_INSTALL_URL],
            capture_output=True,
            text=True,
            check=True,
        )

        subprocess.run(
            ["bash"],
            input=curl.stdout,
            text=True,
            check=True,
        )

        logger.info("Claude Code installed successfully")
        logger.info(
            "You may need to restart your shell or run `source ~/.bashrc` "
            "for the `claude` command to be available"
        )
    except subprocess.CalledProcessError as error:
        logger.warning("Failed to install Claude Code: %s", error)
