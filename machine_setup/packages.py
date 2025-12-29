"""Package installation logic."""

import logging

from machine_setup.config import SetupConfig
from machine_setup.utils import run

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
    """Install packages for the current profile."""
    packages = config.get_packages()

    to_install = [package for package in packages if not is_package_installed(package)]

    if not to_install:
        logger.info("All packages already installed")
        return

    logger.info("Installing %d packages: %s", len(to_install), ", ".join(to_install))

    run(["sudo", "apt-get", "update", "-qq"])

    run(
        [
            "sudo",
            "apt-get",
            "install",
            "-y",
            "-qq",
            "--no-install-recommends",
            *to_install,
        ]
    )

    logger.info("Package installation complete")
