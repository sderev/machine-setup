"""Dotfiles cloning and GNU Stow management."""

import logging
from pathlib import Path

from machine_setup.config import SetupConfig
from machine_setup.utils import run

logger = logging.getLogger("machine_setup")


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
