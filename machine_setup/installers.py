"""Package and tool installation.

Includes apt packages, uv tools, npm tools, Claude Code, locale configuration,
and Quarto installation.
"""

import json
import logging
import os
import subprocess
import tempfile
import urllib.error
import urllib.request

from machine_setup.presets import SetupConfig
from machine_setup.utils import command_exists, run, sudo_prefix

logger = logging.getLogger("machine_setup")

# Locale configuration
LOCALE = "en_US.UTF-8"

# Claude Code installer
CLAUDE_INSTALL_URL = "https://claude.ai/install.sh"


def is_package_installed(package: str) -> bool:
    """Check if a Debian package is installed."""
    result = run(
        ["dpkg-query", "-W", "-f=${Status}", package],
        check=False,
        capture=True,
    )
    return "install ok installed" in result.stdout


def install_packages(config: SetupConfig) -> None:
    """Install packages for the current preset."""
    packages = config.get_packages()

    to_install = [package for package in packages if not is_package_installed(package)]

    if not to_install:
        logger.info("All packages already installed")
        return

    logger.info("Installing %d packages: %s", len(to_install), ", ".join(to_install))

    sudo = sudo_prefix()
    run([*sudo, "apt-get", "update", "-qq"])
    logger.info("Upgrading system packages...")
    run([*sudo, "apt-get", "upgrade", "-y", "-qq"])

    # Preseed msmtp debconf to enable AppArmor and skip interactive prompt
    if "msmtp" in to_install or "msmtp-mta" in to_install:
        subprocess.run(
            [*sudo, "debconf-set-selections"],
            input="msmtp msmtp/apparmor boolean true\n",
            text=True,
            check=True,
        )

    run(
        [
            *sudo,
            "apt-get",
            "install",
            "-y",
            "-qq",
            "--no-install-recommends",
            *to_install,
        ]
    )

    logger.info("Package installation complete")


def install_quarto() -> None:
    """Install Quarto from GitHub releases."""
    if command_exists("quarto"):
        logger.info("Quarto already installed")
        return

    logger.info("Installing Quarto from GitHub releases...")

    api_url = "https://api.github.com/repos/quarto-dev/quarto-cli/releases/latest"
    request = urllib.request.Request(
        api_url,
        headers={"User-Agent": "machine-setup/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status != 200:
                raise RuntimeError(
                    f"GitHub API returned status {response.status} for latest Quarto release"
                )
            release = json.load(response)
    except urllib.error.URLError as exc:
        raise RuntimeError("Failed to fetch Quarto release metadata") from exc

    arch_result = run(["dpkg", "--print-architecture"], capture=True)
    arch = arch_result.stdout.strip()
    asset_suffixes = {
        "amd64": "linux-amd64.deb",
        "arm64": "linux-arm64.deb",
    }
    asset_suffix = asset_suffixes.get(arch)
    if not asset_suffix:
        raise RuntimeError(f"Unsupported architecture for Quarto install: {arch}")

    deb_url = None
    for asset in release["assets"]:
        if asset["name"].endswith(asset_suffix):
            deb_url = asset["browser_download_url"]
            break

    if not deb_url:
        raise RuntimeError("Could not find Quarto .deb in latest release")

    deb_path = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=".deb", delete=False) as tmp:
            logger.info("Downloading %s", deb_url)
            with urllib.request.urlopen(deb_url, timeout=30) as response:
                if response.status != 200:
                    raise RuntimeError(f"Quarto download returned status {response.status}")
                tmp.write(response.read())
            deb_path = tmp.name

        sudo = sudo_prefix()
        run([*sudo, "dpkg", "-i", deb_path])
        logger.info("Quarto installation complete")
    finally:
        if deb_path:
            try:
                os.remove(deb_path)
            except OSError:
                logger.warning("Failed to remove temporary Quarto package: %s", deb_path)


# --- Locale configuration ---


def is_locale_generated(locale: str) -> bool:
    """Check if a locale is already generated."""
    result = run(["locale", "-a"], check=True, capture=True)
    return locale.replace("UTF-8", "utf8") in result.stdout


def generate_locale(locale: str) -> None:
    """Generate specified locale using locale-gen."""
    logger.info("Generating locale: %s", locale)
    sudo = sudo_prefix()

    sed_escape = locale.replace(".", "\\.")

    run(
        [
            *sudo,
            "sed",
            "-i",
            "-e",
            f"s/^# *{sed_escape}/{locale}/",
            "/etc/locale.gen",
        ]
    )
    run([*sudo, "locale-gen"])
    logger.info("Locale generation complete")


def setup_locale() -> None:
    """Configure UTF-8 locale."""
    if is_locale_generated(LOCALE):
        logger.info("Locale %s already generated", LOCALE)
        return

    locale_gen = run(["which", "locale-gen"], check=False, capture=True)
    if locale_gen.returncode != 0:
        logger.warning("locale-gen not found; skipping locale configuration")
        return

    generate_locale(LOCALE)


# --- uv tools ---


def install_uv_tools(tools: list[str]) -> None:
    """Install Python tools using uv tool install."""
    if not tools:
        logger.info("No uv tools to install")
        return

    if not command_exists("uv"):
        logger.warning("uv not found; skipping uv tool installation")
        return

    for tool in tools:
        logger.info("Installing %s via uv tool...", tool)
        result = run(["uv", "tool", "install", tool], check=False)
        if result.returncode != 0:
            logger.warning("uv tool install failed for %s", tool)


# --- npm tools ---


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


# --- Claude Code ---


def install_claude_code() -> None:
    """Install Claude Code CLI via native binary installer."""
    if command_exists("claude"):
        logger.info("Claude Code already installed")
        return

    logger.info("Installing Claude Code CLI...")

    try:
        curl = subprocess.run(
            ["curl", "-fsSL", "--max-time", "30", CLAUDE_INSTALL_URL],
            capture_output=True,
            text=True,
            check=True,
        )

        subprocess.run(
            ["bash"],
            input=curl.stdout,
            text=True,
            check=True,
        )

        logger.info("Claude Code installed successfully")
        logger.info(
            "You may need to restart your shell or run `source ~/.bashrc` "
            "for the `claude` command to be available"
        )
    except subprocess.CalledProcessError as error:
        logger.warning("Failed to install Claude Code: %s", error)


# --- Go tools (SCC) ---


def install_scc() -> None:
    """Install SCC (code counter) via go install."""
    if command_exists("scc"):
        logger.info("SCC already installed")
        return

    if not command_exists("go"):
        logger.warning("Go not found; skipping SCC installation")
        return

    logger.info("Installing SCC via go install...")

    result = run(
        ["go", "install", "github.com/boyter/scc/v3@latest"],
        check=False,
    )

    if result.returncode != 0:
        logger.warning("Failed to install SCC")
    else:
        logger.info("SCC installed successfully")
