"""Shell configuration - set zsh as default."""

import logging
import os
from pathlib import Path

from machine_setup.utils import command_exists, run

logger = logging.getLogger("machine_setup")


def get_current_shell() -> str:
    """Get current user's default shell."""
    return os.environ.get("SHELL", "/bin/bash")


def get_zsh_path() -> str | None:
    """Get path to zsh binary."""
    result = run(["which", "zsh"], check=False, capture=True)
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def set_default_shell_zsh() -> None:
    """Set zsh as the default shell for current user."""
    current_shell = get_current_shell()

    if "zsh" in current_shell:
        logger.info("zsh is already the default shell")
        return

    zsh_path = get_zsh_path()
    if not zsh_path:
        logger.error("zsh not found in PATH")
        return

    shells_file = Path("/etc/shells")
    if shells_file.exists():
        shells_content = shells_file.read_text()
        if zsh_path not in shells_content:
            logger.info("Adding %s to /etc/shells", zsh_path)
            run(["sudo", "sh", "-c", f"echo '{zsh_path}' >> /etc/shells"])

    logger.info("Setting default shell to zsh...")
    run(["chsh", "-s", zsh_path])

    logger.info("Default shell changed to zsh (effective on next login)")


def setup_shell() -> None:
    """Complete shell setup."""
    if command_exists("zsh"):
        set_default_shell_zsh()
    else:
        logger.warning("zsh not installed, cannot set as default shell")
