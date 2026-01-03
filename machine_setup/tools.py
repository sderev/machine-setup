"""Python tool installation with uv."""

import logging
from concurrent.futures import ThreadPoolExecutor

from machine_setup.utils import command_exists, run

logger = logging.getLogger("machine_setup")


def install_uv_tools(tools: list[str], parallel: bool = False) -> None:
    """Install Python tools using uv tool install."""
    if not tools:
        logger.info("No uv tools to install")
        return

    if not command_exists("uv"):
        logger.warning("uv not found; skipping uv tool installation")
        return

    def install_tool(tool: str) -> None:
        logger.info("Installing %s via uv tool...", tool)
        run(["uv", "tool", "install", tool], check=False)

    if parallel:
        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(install_tool, tools))
    else:
        for tool in tools:
            install_tool(tool)
