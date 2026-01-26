"""Package installation logic."""

import json
import logging
import os
import subprocess
import tempfile
import urllib.error
import urllib.request

from machine_setup.config import SetupConfig
from machine_setup.utils import command_exists, run, sudo_prefix

logger = logging.getLogger("machine_setup")


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
