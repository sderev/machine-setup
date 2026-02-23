"""WSL detection and Windows configuration setup."""

import hashlib
import logging
import os
import shutil
import tempfile
from pathlib import Path

from machine_setup.utils import run, sudo_prefix

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib  # type: ignore[import-not-found]

logger = logging.getLogger("machine_setup")

BOOTSTRAP_STATE_RELATIVE_PATH = Path(".config") / "machine-setup" / "bootstrap.toml"


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


def get_bootstrap_state_path(home: Path | None = None) -> Path:
    """Return local bootstrap state path."""
    state_home = home if home is not None else Path.home()
    return state_home / BOOTSTRAP_STATE_RELATIVE_PATH


def load_bootstrap_state(state_path: Path | None = None) -> dict[str, object]:
    """Load local bootstrap state from TOML."""
    path = state_path if state_path is not None else get_bootstrap_state_path()
    if not path.exists():
        return {}

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as error:
        logger.warning("Could not read bootstrap state at %s: %s", path, error)
        return {}

    try:
        parsed = tomllib.loads(raw)
    except Exception as error:
        logger.warning("Ignoring invalid bootstrap state at %s: %s", path, error)
        return {}

    if not isinstance(parsed, dict):
        logger.warning("Ignoring invalid bootstrap state at %s: root must be a TOML table", path)
        return {}

    state: dict[str, object] = {}
    if isinstance(parsed.get("dotfiles_repo"), str):
        state["dotfiles_repo"] = parsed["dotfiles_repo"]
    if isinstance(parsed.get("dotfiles_branch"), str):
        state["dotfiles_branch"] = parsed["dotfiles_branch"]
    if isinstance(parsed.get("apply_wslconfig"), bool):
        state["apply_wslconfig"] = parsed["apply_wslconfig"]
    if isinstance(parsed.get("wslconfig_source_checksum"), str):
        state["wslconfig_source_checksum"] = parsed["wslconfig_source_checksum"]
    return state


def save_bootstrap_state(
    state: dict[str, object],
    state_path: Path | None = None,
) -> Path:
    """Persist local bootstrap state as TOML."""
    path = state_path if state_path is not None else get_bootstrap_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    if isinstance(state.get("dotfiles_repo"), str):
        lines.append(f'dotfiles_repo = "{_toml_escape(state["dotfiles_repo"])}"')
    if isinstance(state.get("dotfiles_branch"), str):
        lines.append(f'dotfiles_branch = "{_toml_escape(state["dotfiles_branch"])}"')
    if isinstance(state.get("apply_wslconfig"), bool):
        value = "true" if state["apply_wslconfig"] else "false"
        lines.append(f"apply_wslconfig = {value}")
    if isinstance(state.get("wslconfig_source_checksum"), str):
        escaped = _toml_escape(state["wslconfig_source_checksum"])
        lines.append(f'wslconfig_source_checksum = "{escaped}"')

    content = "\n".join(lines)
    if content:
        content += "\n"
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.tmp-", dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, path)
        os.chmod(path, 0o600)
    except OSError:
        tmp_path.unlink(missing_ok=True)
        raise
    return path


def get_wsl_conf_source(dotfiles_path: Path) -> Path:
    """Get `/etc/wsl.conf` source file path from dotfiles."""
    return dotfiles_path / "machine-setup" / "wsl" / "wsl.conf"


def get_wslconfig_source(dotfiles_path: Path) -> Path:
    """Get `%UserProfile%\\.wslconfig` source file path from dotfiles."""
    return dotfiles_path / "machine-setup" / "wsl" / ".wslconfig"


def compute_file_checksum(path: Path) -> str:
    """Compute SHA256 checksum for file content."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def deploy_wsl_conf(dotfiles_path: Path) -> bool:
    """Deploy `/etc/wsl.conf` from private dotfiles when available."""
    source_path = get_wsl_conf_source(dotfiles_path)
    target_path = Path("/etc/wsl.conf")

    if not source_path.exists():
        logger.info("WSL distro config not found at %s, skipping", source_path)
        return False

    try:
        source_bytes = source_path.read_bytes()
    except OSError as error:
        logger.warning("Could not read WSL distro config %s: %s", source_path, error)
        return False

    if target_path.exists():
        try:
            if source_bytes == target_path.read_bytes():
                logger.info("%s already up to date", target_path)
                return False
        except OSError as error:
            logger.warning("Could not compare %s: %s", target_path, error)

    if os.geteuid() == 0:
        try:
            shutil.copy2(source_path, target_path)
            target_path.chmod(0o644)
        except OSError as error:
            logger.warning("Could not deploy %s: %s", target_path, error)
            return False
    else:
        sudo = sudo_prefix()
        result = run(
            [*sudo, "install", "-m", "644", str(source_path), str(target_path)],
            check=False,
            capture=True,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip() if result.stderr else "unknown error"
            logger.warning("Could not deploy %s with sudo: %s", target_path, stderr)
            return False

    logger.info("Installed WSL distro config: %s", target_path)
    return True


def get_windows_wslconfig_path(username: str) -> Path:
    """Get Windows host `.wslconfig` path."""
    return Path(f"/mnt/c/Users/{username}/.wslconfig")


def deploy_wslconfig(dotfiles_path: Path, username: str) -> bool:
    """Deploy host `.wslconfig` from private dotfiles."""
    source_path = get_wslconfig_source(dotfiles_path)
    target_path = get_windows_wslconfig_path(username)

    if not source_path.exists():
        logger.info("WSL host config not found at %s, skipping", source_path)
        return False

    try:
        source_bytes = source_path.read_bytes()
    except OSError as error:
        logger.warning("Could not read WSL host config %s: %s", source_path, error)
        return False

    changed = True
    if target_path.exists():
        try:
            changed = target_path.read_bytes() != source_bytes
        except OSError as error:
            logger.warning("Could not compare %s: %s", target_path, error)

    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)
    except OSError as error:
        logger.warning("Could not deploy %s: %s", target_path, error)
        return False

    if changed:
        logger.info("Installed Windows host WSL config: %s", target_path)
    else:
        logger.info("Windows host WSL config already up to date: %s", target_path)
    return changed


def _toml_escape(value: object) -> str:
    text = str(value)
    return text.replace("\\", "\\\\").replace('"', '\\"')


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
