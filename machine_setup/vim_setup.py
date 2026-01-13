"""Vim plugin installation using vim-plug."""

import logging
from pathlib import Path

from machine_setup.utils import command_exists, run

logger = logging.getLogger("machine_setup")

VIM_PLUG_URL = "https://raw.githubusercontent.com/junegunn/vim-plug/master/plug.vim"
VIM_PLUG_PATH = Path.home() / ".vim" / "autoload" / "plug.vim"


def install_vim_plug() -> None:
    """Install vim-plug if not present."""
    if VIM_PLUG_PATH.exists():
        logger.debug("vim-plug already installed")
        return

    if not command_exists("curl"):
        logger.warning("curl not found, cannot download vim-plug")
        return

    logger.info("Installing vim-plug...")
    VIM_PLUG_PATH.parent.mkdir(parents=True, exist_ok=True)

    run(
        [
            "curl",
            "-fLo",
            str(VIM_PLUG_PATH),
            "--create-dirs",
            VIM_PLUG_URL,
        ]
    )


def install_vim_plugins() -> None:
    """Install vim plugins using vim-plug."""
    if not command_exists("vim"):
        logger.warning("vim not installed, skipping plugin installation")
        return

    install_vim_plug()

    logger.info("Installing vim plugins...")
    run(
        [
            "vim",
            "-E",
            "-s",
            "-c",
            "PlugInstall",
            "-c",
            "qa!",
        ],
        check=False,
    )

    logger.info("Vim plugins installed")


def setup_vim() -> None:
    """Complete vim setup."""
    install_vim_plugins()

    undo_dir = Path.home() / ".vim" / "undo-dir"
    undo_dir.mkdir(parents=True, exist_ok=True)
    undo_dir.chmod(0o700)
