"""Python tool installation with uv."""

import logging

from machine_setup.utils import command_exists, run

logger = logging.getLogger("machine_setup")


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
