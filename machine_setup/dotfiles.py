"""Dotfiles cloning and GNU Stow management."""

import logging
import shutil
from datetime import datetime
from pathlib import Path

from machine_setup.config import SetupConfig
from machine_setup.utils import command_exists, run

logger = logging.getLogger("machine_setup")


def remove_default_dotfiles(home: Path) -> None:
    """Remove skeleton/default dotfiles that conflict with stow."""
    default_dotfiles = (
        ".bashrc",
        ".profile",
        ".bash_logout",
        ".gitconfig",
    )

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


def ensure_github_auth(repo_url: str) -> None:
    """Ensure gh auth for GitHub HTTPS repos."""
    if not repo_url.startswith("https://github.com/"):
        return

    if not command_exists("gh"):
        logger.warning("gh CLI not found; HTTPS clone may require manual credentials")
        return

    status = run(["gh", "auth", "status", "--hostname", "github.com"], check=False, capture=True)
    if status.returncode != 0:
        logger.info("Authenticating to GitHub via device flow...")
        run(
            ["gh", "auth", "login", "--hostname", "github.com", "--git-protocol", "https"],
            check=True,
        )

    run(["gh", "auth", "setup-git"], check=False)


def clone_dotfiles(config: SetupConfig) -> Path:
    """Clone dotfiles repo if not present."""
    dotfiles_path = Path(config.dotfiles_dir).expanduser()
    target_branch = config.dotfiles_branch
    repo_url = config.dotfiles_repo

    if dotfiles_path.exists():
        result = run(
            ["git", "-C", str(dotfiles_path), "remote", "get-url", "origin"],
            check=False,
            capture=True,
        )
        if result.returncode == 0:
            repo_url = result.stdout.strip()

    ensure_github_auth(repo_url)

    if dotfiles_path.exists():
        logger.info("Dotfiles already cloned at %s", dotfiles_path)
        # Ensure we're on the requested branch
        run(["git", "-C", str(dotfiles_path), "checkout", target_branch])
        pull_result = run(
            ["git", "-C", str(dotfiles_path), "pull", "--ff-only"],
            check=False,
        )
        if pull_result.returncode != 0:
            logger.warning("Dotfiles repo not updated; `git pull --ff-only` failed.")
        return dotfiles_path

    logger.info("Cloning dotfiles from %s (branch: %s)", config.dotfiles_repo, target_branch)
    run(["git", "clone", "--branch", target_branch, config.dotfiles_repo, str(dotfiles_path)])

    return dotfiles_path


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
