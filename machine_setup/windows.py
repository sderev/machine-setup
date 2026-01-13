"""WSL detection and Windows configuration setup."""

import logging
import os
import shutil
from pathlib import Path

from machine_setup.utils import run

logger = logging.getLogger("machine_setup")


def is_wsl() -> bool:
    """Detect if running inside WSL."""
    # Method 1: Check /proc/version
    try:
        with open("/proc/version") as f:
            version = f.read().lower()
            if "microsoft" in version or "wsl" in version:
                return True
    except FileNotFoundError:
        pass

    # Method 2: Check WSL_DISTRO_NAME env var
    return bool(os.environ.get("WSL_DISTRO_NAME"))


def get_windows_username() -> str | None:
    """Get Windows username from /mnt/c/Users/."""
    users_path = Path("/mnt/c/Users")
    if not users_path.exists():
        return None

    # Skip system folders
    skip = {"Public", "Default", "Default User", "All Users"}

    # Get current Linux user to prefer matching Windows username
    current_user = os.environ.get("USER")

    fallback_username = None
    for user_dir in sorted(users_path.iterdir(), key=lambda path: path.name):
        # Verify it looks like a real user folder with AppData
        is_valid_user_dir = (
            user_dir.is_dir() and user_dir.name not in skip and (user_dir / "AppData").exists()
        )
        if not is_valid_user_dir:
            continue

        username = user_dir.name

        # Path traversal validation: reject usernames with dangerous characters
        if ".." in username or "/" in username or "\\" in username:
            continue

        # Prefer username matching current Linux user
        if current_user and username == current_user:
            return username

        # Track first valid user as fallback
        if fallback_username is None:
            fallback_username = username

    return fallback_username


def get_windows_startup_folder(username: str) -> Path:
    """Get Windows Startup folder path."""
    return Path(
        f"/mnt/c/Users/{username}/AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Startup"
    )


def get_windows_terminal_settings(username: str) -> Path:
    """Get Windows Terminal settings.json path."""
    return Path(
        f"/mnt/c/Users/{username}/AppData/Local/Packages"
        f"/Microsoft.WindowsTerminal_8wekyb3d8bbwe/LocalState/settings.json"
    )


def install_winget_package(package_id: str) -> bool:
    """Install a package via winget.

    Returns True if installation succeeded or package already installed.
    """
    try:
        result = run(
            [
                "cmd.exe",
                "/c",
                "winget",
                "install",
                "-e",
                "--id",
                package_id,
                "--accept-package-agreements",
                "--accept-source-agreements",
            ],
            check=False,
            capture=True,
        )
    except FileNotFoundError as error:
        logger.warning("winget install failed; cmd.exe not available: %s", error)
        return False

    return result.returncode == 0


def setup_windows_configs(dotfiles_path: Path) -> None:
    """Copy Windows configs from dotfiles to appropriate locations."""
    if not is_wsl():
        logger.debug("Not running in WSL, skipping Windows setup")
        return

    username = get_windows_username()
    if not username:
        logger.warning("Could not detect Windows username, skipping Windows setup")
        return

    logger.info("Detected Windows user: %s", username)

    # Install AutoHotkey and copy script to Startup
    ahk_src = dotfiles_path / "windows" / "startup" / "remapping.ahk"
    if ahk_src.exists():
        logger.info("Installing AutoHotkey via winget...")
        if install_winget_package("AutoHotkey.AutoHotkey"):
            startup_folder = get_windows_startup_folder(username)
            if startup_folder.exists():
                ahk_dst = startup_folder / "remapping.ahk"
                shutil.copy2(ahk_src, ahk_dst)
                logger.info("Installed %s to Windows Startup", ahk_src.name)
            else:
                logger.warning("Windows Startup folder not found: %s", startup_folder)
        else:
            logger.warning("Failed to install AutoHotkey via winget")

    # Copy Windows Terminal settings
    wt_src = dotfiles_path / "windows" / "windows_terminal" / "settings.json"
    wt_dst = get_windows_terminal_settings(username)
    if wt_src.exists():
        if wt_dst.parent.exists():
            shutil.copy2(wt_src, wt_dst)
            logger.info("Installed Windows Terminal settings")
        else:
            logger.debug("Windows Terminal not installed, skipping settings copy")
