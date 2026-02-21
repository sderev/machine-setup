"""WSL detection and Windows configuration setup."""

import logging
import os
import shutil
from pathlib import Path

from machine_setup.utils import run

logger = logging.getLogger("machine_setup")


TASKBAR_PINNING_SCRIPT = """
$ErrorActionPreference = 'Stop'

function Invoke-TaskbarVerb {
    param(
        [Parameter(Mandatory = $true)] $Item,
        [Parameter(Mandatory = $true)][string[]] $Patterns
    )

    foreach ($verb in @($Item.Verbs())) {
        $cleanName = ($verb.Name -replace '&', '').ToLowerInvariant()
        foreach ($pattern in $Patterns) {
            if ($cleanName -like "*$pattern*") {
                $verb.DoIt()
                Start-Sleep -Milliseconds 200
                return $true
            }
        }
    }

    return $false
}

$shell = New-Object -ComObject Shell.Application
$appsFolder = $shell.Namespace('shell:AppsFolder')
$pinPatterns = @('pin to taskbar', 'taskbarpin', 'epingler a la barre des taches')
$unpinPatterns = @('unpin from taskbar', 'taskbarunpin', 'detacher de la barre des taches')

$targets = @(
    @{ Name = 'Chrome'; Type = 'desktop'; Paths = @(
        'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
        "$env:LOCALAPPDATA\\Google\\Chrome\\Application\\chrome.exe"
    )},
    @{ Name = 'Brave'; Type = 'desktop'; Paths = @(
        'C:\\Program Files\\BraveSoftware\\Brave-Browser\\Application\\brave.exe',
        "$env:LOCALAPPDATA\\BraveSoftware\\Brave-Browser\\Application\\brave.exe"
    )},
    @{ Name = 'Windows Terminal'; Type = 'appx';
       AppId = 'Microsoft.WindowsTerminal_8wekyb3d8bbwe!App' },
    @{ Name = 'Windows Clock'; Type = 'appx'; AppId = 'Microsoft.WindowsAlarms_8wekyb3d8bbwe!App' },
    @{ Name = 'Calculator'; Type = 'appx'; AppId = 'Microsoft.WindowsCalculator_8wekyb3d8bbwe!App' }
)

$missing = New-Object System.Collections.Generic.List[string]
$failed = New-Object System.Collections.Generic.List[string]

foreach ($target in $targets) {
    $item = $null

    if ($target.Type -eq 'desktop') {
        foreach ($candidatePath in $target.Paths) {
            if (-not (Test-Path -LiteralPath $candidatePath)) {
                continue
            }

            $directory = Split-Path -Path $candidatePath
            $name = Split-Path -Path $candidatePath -Leaf
            $item = $shell.Namespace($directory).ParseName($name)
            if ($item) {
                break
            }
        }
    } else {
        $item = $appsFolder.ParseName($target.AppId)
    }

    if (-not $item) {
        $missing.Add($target.Name)
        continue
    }

    # Keep run deterministic: unpin first, then pin in desired order.
    [void](Invoke-TaskbarVerb -Item $item -Patterns $unpinPatterns)
    if (-not (Invoke-TaskbarVerb -Item $item -Patterns $pinPatterns)) {
        $failed.Add($target.Name)
    }
}

if ($missing.Count -gt 0 -or $failed.Count -gt 0) {
    $errors = New-Object System.Collections.Generic.List[string]
    if ($missing.Count -gt 0) {
        $errors.Add("Missing apps: " + ($missing -join ', '))
    }
    if ($failed.Count -gt 0) {
        $errors.Add("Could not pin apps: " + ($failed -join ', '))
    }
    throw ($errors -join '; ')
}
"""


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


def get_windows_fonts_dir(username: str) -> Path:
    """Get Windows per-user fonts directory path."""
    return Path(f"/mnt/c/Users/{username}/AppData/Local/Microsoft/Windows/Fonts")


def get_windows_terminal_settings(username: str) -> Path:
    """Get Windows Terminal settings.json path."""
    return Path(
        f"/mnt/c/Users/{username}/AppData/Local/Packages"
        f"/Microsoft.WindowsTerminal_8wekyb3d8bbwe/LocalState/settings.json"
    )


def get_filepilot_config(username: str) -> Path:
    """Get File Pilot config path."""
    return Path(f"/mnt/c/Users/{username}/AppData/Roaming/Voidstar/FilePilot/FPilot-Config.json")


def get_machine_setup_state_dir(username: str) -> Path:
    """Get machine-setup state directory on Windows."""
    return Path(f"/mnt/c/Users/{username}/AppData/Local/machine-setup")


def get_taskbar_pinning_sentinel(username: str) -> Path:
    """Get one-time taskbar pinning sentinel path."""
    return get_machine_setup_state_dir(username) / "taskbar-pinning-v1.done"


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


def pin_taskbar_apps() -> bool:
    """Pin taskbar apps in target order via PowerShell."""
    try:
        result = run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                TASKBAR_PINNING_SCRIPT,
            ],
            check=False,
            capture=False,
        )
    except FileNotFoundError as error:
        logger.warning("Taskbar pinning failed; powershell.exe not available: %s", error)
        return False

    if result.returncode != 0:
        logger.warning("Taskbar pinning command failed with exit code %s", result.returncode)
        return False

    return True


def pin_taskbar_apps_once(username: str) -> None:
    """Apply taskbar pinning once and record sentinel on Windows side."""
    sentinel = get_taskbar_pinning_sentinel(username)
    if sentinel.exists():
        logger.debug("Taskbar pinning already attempted, skipping")
        return

    logger.info("Applying one-time taskbar pinning")
    if pin_taskbar_apps():
        logger.info("Taskbar pinning applied")
    else:
        logger.warning("Taskbar pinning failed; continuing setup")

    try:
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.write_text("taskbar-pinning-v1\n", encoding="utf-8")
    except OSError as error:
        logger.warning("Could not persist taskbar pinning state at %s: %s", sentinel, error)


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

    logger.info("Installing Google Chrome via winget...")
    if install_winget_package("Google.Chrome"):
        logger.info("Google Chrome installed successfully")
    else:
        logger.warning("Failed to install Google Chrome via winget")

    logger.info("Installing Brave via winget...")
    if install_winget_package("Brave.Brave"):
        logger.info("Brave installed successfully")
    else:
        logger.warning("Failed to install Brave via winget")

    logger.info("Installing Proton Pass via winget...")
    if install_winget_package("Proton.ProtonPass"):
        logger.info("Proton Pass installed successfully")
    else:
        logger.warning("Failed to install Proton Pass via winget")

    logger.info("Installing VLC via winget...")
    if install_winget_package("VideoLAN.VLC"):
        logger.info("VLC installed successfully")
    else:
        logger.warning("Failed to install VLC via winget")

    logger.info("Installing Windows Terminal via winget...")
    if install_winget_package("Microsoft.WindowsTerminal"):
        logger.info("Windows Terminal installed successfully")
    else:
        logger.warning("Failed to install Windows Terminal via winget")

    # Copy Windows Terminal settings
    wt_src = dotfiles_path / "windows" / "windows_terminal" / "settings.json"
    wt_dst = get_windows_terminal_settings(username)
    if wt_src.exists():
        if wt_dst.parent.exists():
            shutil.copy2(wt_src, wt_dst)
            logger.info("Installed Windows Terminal settings")
        else:
            logger.debug("Windows Terminal not installed, skipping settings copy")

    # Install PowerToys
    logger.info("Installing PowerToys via winget...")
    if install_winget_package("Microsoft.PowerToys"):
        logger.info("PowerToys installed successfully")
    else:
        logger.warning("Failed to install PowerToys via winget")

    # Install File Pilot and copy config
    logger.info("Installing File Pilot via winget...")
    if install_winget_package("Voidstar.FilePilot"):
        logger.info("File Pilot installed successfully")
    else:
        logger.warning("Failed to install File Pilot via winget")

    fp_src = dotfiles_path / "windows" / "filepilot" / "FPilot-Config.json"
    if fp_src.exists():
        fp_dst = get_filepilot_config(username)
        if fp_dst.parent.exists():
            shutil.copy2(fp_src, fp_dst)
            logger.info("Installed File Pilot config")
        else:
            logger.debug("File Pilot not installed, skipping config copy")

    pin_taskbar_apps_once(username)
