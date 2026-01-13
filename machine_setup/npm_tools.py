"""Npm tool installation for global tools."""

import logging

from machine_setup.utils import command_exists, run, sudo_prefix

logger = logging.getLogger("machine_setup")


def install_npm_tools(tools: list[str]) -> None:
    """Install npm tools using npm install -g."""
    if not tools:
        logger.info("No npm tools to install")
        return

    if not command_exists("npm"):
        logger.warning("npm not found; skipping npm tool installation")
        return

    sudo = sudo_prefix()
    for tool in tools:
        logger.info("Installing %s via npm...", tool)
        result = run([*sudo, "npm", "install", "-g", tool], check=False)
        if result.returncode != 0:
            logger.warning("npm tool install failed for %s", tool)
