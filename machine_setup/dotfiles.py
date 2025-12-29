"""Dotfiles cloning and GNU Stow management."""

import logging
import shutil
from datetime import datetime
from pathlib import Path

from machine_setup.config import SetupConfig
from machine_setup.utils import run

logger = logging.getLogger("machine_setup")


def remove_default_dotfiles(home: Path) -> None:
    """Remove shell skeleton files that conflict with stow."""
    default_dotfiles = (".bashrc", ".profile", ".bash_logout")

    for dotfile in default_dotfiles:
        target = home / dotfile
        if target.is_symlink():
            continue
        if target.is_file():
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            backup_path = target.with_name(f"{target.name}.bak.{timestamp}")
            suffix = 0
            while backup_path.exists():
                suffix += 1
                backup_path = target.with_name(f"{target.name}.bak.{timestamp}.{suffix}")
            logger.info("Backing up %s to %s before stow", target, backup_path)
            shutil.move(str(target), backup_path)


def clone_dotfiles(config: SetupConfig) -> Path:
    """Clone dotfiles repo if not present."""
    dotfiles_path = Path(config.dotfiles_dir).expanduser()

    if dotfiles_path.exists():
        logger.info("Dotfiles already cloned at %s", dotfiles_path)
        run(["git", "-C", str(dotfiles_path), "pull", "--ff-only"], check=False)
        return dotfiles_path

    logger.info("Cloning dotfiles from %s", config.dotfiles_repo)
    run(["git", "clone", config.dotfiles_repo, str(dotfiles_path)])

    return dotfiles_path


def backup_existing_file(path: Path) -> None:
    """Backup existing file before stowing."""
    if path.exists() and not path.is_symlink():
        backup_path = path.with_suffix(f"{path.suffix}.bak")
        logger.info("Backing up %s to %s", path, backup_path)
        path.rename(backup_path)


def stow_dotfiles(config: SetupConfig, dotfiles_path: Path) -> None:
    """Symlink dotfiles using GNU Stow."""
    home = Path(config.home_dir).expanduser()
    stow_packages = config.get_stow_packages()

    remove_default_dotfiles(home)

    logger.info("Stowing packages: %s", ", ".join(stow_packages))

    for package in stow_packages:
        package_path = dotfiles_path / package
        if not package_path.exists():
            logger.warning("Stow package %s not found, skipping", package)
            continue

        logger.debug("Stowing %s", package)
        run(
            [
                "stow",
                "--verbose=1",
                "--dir",
                str(dotfiles_path),
                "--target",
                str(home),
                "--restow",
                "--no-folding",
                package,
            ]
        )

    logger.info("Dotfiles stowed successfully")
