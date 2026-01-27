"""SSH key generation and GitHub registration."""

import logging
import socket
from datetime import datetime
from pathlib import Path

from machine_setup.utils import command_exists, run

logger = logging.getLogger("machine_setup")


def generate_key_name() -> str:
    """Generate a descriptive key name with hostname and date.

    Format: machine-setup-{hostname}-{YYYYMMDD}
    """
    hostname = socket.gethostname()
    date_str = datetime.now().strftime("%Y%m%d")
    return f"machine-setup-{hostname}-{date_str}"


def generate_ssh_key(key_name: str = "id_ed25519") -> bool:
    """Generate a new SSH key if one doesn't exist."""
    if not command_exists("ssh-keygen"):
        logger.warning("ssh-keygen not found, cannot generate SSH key")
        return False

    ssh_dir = Path.home() / ".ssh"
    ssh_dir.mkdir(mode=0o700, exist_ok=True)
    ssh_dir.chmod(0o700)

    private_key_path = ssh_dir / key_name
    public_key_path = ssh_dir / f"{key_name}.pub"

    if private_key_path.exists() and public_key_path.exists():
        logger.info("SSH key already exists at %s", private_key_path)
        return True

    if private_key_path.exists() and not public_key_path.exists():
        logger.info("Public key missing, regenerating from %s", private_key_path)
        result = run(
            ["ssh-keygen", "-y", "-P", "", "-f", str(private_key_path)],
            check=False,
            capture=True,
        )
        public_key = result.stdout.strip()
        if result.returncode != 0 or not public_key:
            logger.error("Failed to derive public key from %s", private_key_path)
            return False

        public_key_path.write_text(f"{public_key}\n")
        public_key_path.chmod(0o644)
        logger.info("Public key restored at %s", public_key_path)
        return True

    if public_key_path.exists() and not private_key_path.exists():
        logger.warning(
            "Public key exists without private key at %s, refusing to overwrite",
            public_key_path,
        )
        return False

    logger.info("Generating new SSH key...")
    logger.warning("SSH key will be created WITHOUT a passphrase for automation")
    result = run(
        ["ssh-keygen", "-t", "ed25519", "-f", str(private_key_path), "-N", ""],
        check=False,
    )

    if result.returncode != 0:
        logger.error("Failed to generate SSH key")
        return False

    private_key_path.chmod(0o600)
    logger.info("SSH key generated at %s", private_key_path)
    return True


def _ensure_gh_authenticated(scopes: str = "admin:public_key") -> bool:
    """Ensure gh CLI is authenticated with required scopes."""
    result = run(["gh", "auth", "status", "--hostname", "github.com"], check=False, capture=True)
    if result.returncode != 0:
        logger.info("Authenticating to GitHub via device flow...")
        login_result = run(
            [
                "gh",
                "auth",
                "login",
                "--hostname",
                "github.com",
                "--git-protocol",
                "https",
                "--scopes",
                scopes,
            ],
            check=False,
        )
        if login_result.returncode != 0:
            logger.warning("gh CLI authentication failed")
            return False
    return True


def _refresh_gh_scopes(scopes: str) -> bool:
    """Refresh GitHub auth scopes."""
    logger.info("Refreshing GitHub auth scopes to include %s...", scopes)
    refresh_result = run(
        [
            "gh",
            "auth",
            "refresh",
            "--hostname",
            "github.com",
            "--scopes",
            scopes,
        ],
        check=False,
    )
    return refresh_result.returncode == 0


def add_ssh_key_to_github(key_name: str = "id_ed25519", title: str | None = None) -> bool:
    """Add SSH public key to GitHub using gh CLI."""
    if not command_exists("gh"):
        logger.warning("gh CLI not found, cannot add SSH key to GitHub")
        return False

    public_key_path = Path.home() / ".ssh" / f"{key_name}.pub"

    if not public_key_path.exists():
        logger.warning("SSH public key not found at %s", public_key_path)
        return False

    if not _ensure_gh_authenticated("admin:public_key"):
        logger.warning("Cannot add SSH key without GitHub authentication")
        return False

    if title is None:
        title = generate_key_name()

    logger.info("Adding SSH key to GitHub with title '%s'...", title)
    result = run(
        ["gh", "ssh-key", "add", str(public_key_path), "--title", title],
        check=False,
        capture=True,
    )

    if result.returncode != 0:
        # Duplicate key is not an error
        duplicate_hint = f"{result.stdout}{result.stderr}".lower()
        if "already" in duplicate_hint:
            logger.info("SSH key already registered with GitHub")
            return True
        if "http 404" in duplicate_hint or "status 404" in duplicate_hint:
            if not _refresh_gh_scopes("admin:public_key"):
                logger.warning("Failed to refresh GitHub auth scopes")
                return False
            result = run(
                ["gh", "ssh-key", "add", str(public_key_path), "--title", title],
                check=False,
                capture=True,
            )
            if result.returncode != 0:
                duplicate_hint = f"{result.stdout}{result.stderr}".lower()
                if "already" in duplicate_hint:
                    logger.info("SSH key already registered with GitHub")
                    return True
                logger.warning("Failed to add SSH key to GitHub: %s", result.stderr.strip())
                return False
            logger.info("SSH key added to GitHub")
            return True
        logger.warning("Failed to add SSH key to GitHub: %s", result.stderr.strip())
        return False

    logger.info("SSH key added to GitHub")
    return True


def setup_ssh(generate: bool = False) -> None:
    """Setup SSH key optionally."""
    if not generate:
        logger.info("SSH key generation skipped (use --generate-ssh-key to enable)")
        return

    if generate_ssh_key():
        key_title = generate_key_name()
        add_ssh_key_to_github(title=key_title)
