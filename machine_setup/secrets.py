"""SSH and GPG key generation and GitHub registration."""

import logging
import os
import socket
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from machine_setup.keys import KeyRecord, KeyRegistry
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


def get_ssh_key_fingerprint(key_name: str = "id_ed25519") -> str | None:
    """Get the fingerprint of an SSH key."""
    if not command_exists("ssh-keygen"):
        return None

    public_key_path = Path.home() / ".ssh" / f"{key_name}.pub"
    if not public_key_path.exists():
        return None

    result = run(
        ["ssh-keygen", "-l", "-f", str(public_key_path)],
        check=False,
        capture=True,
    )

    if result.returncode != 0:
        return None

    # Output format: "256 SHA256:xxx comment (ED25519)"
    parts = result.stdout.strip().split()
    if len(parts) >= 2:
        return parts[1]  # SHA256:xxx
    return None


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


@dataclass
class GpgKeyResult:
    """Result of GPG key generation."""

    fingerprint: str
    key_name: str


def generate_gpg_key(email: str, expiry_days: int = 90) -> GpgKeyResult | None:
    """Generate a new GPG key with expiry.

    Returns a GpgKeyResult with fingerprint and key_name on success, None on failure.
    """
    if not command_exists("gpg"):
        logger.warning("gpg not found, cannot generate GPG key")
        return None

    key_name = generate_key_name()

    # GPG batch configuration for unattended key generation
    # Name-Real uses the same format as SSH key titles for consistency
    gpg_config = f"""
Key-Type: eddsa
Key-Curve: ed25519
Key-Usage: sign
Subkey-Type: ecdh
Subkey-Curve: cv25519
Subkey-Usage: encrypt
Name-Real: {key_name}
Name-Email: {email}
Expire-Date: {expiry_days}d
%no-protection
%commit
"""

    logger.info("Generating new GPG key (expires in %d days)...", expiry_days)
    logger.warning("GPG key will be created WITHOUT a passphrase for automation")

    # Write config to temp file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".gpg-gen", delete=False) as f:
        f.write(gpg_config)
        config_path = f.name

    try:
        # Generate key with batch mode
        env = os.environ.copy()
        # Prevent pinentry from popping up
        env["GPG_TTY"] = ""

        result = run(
            ["gpg", "--batch", "--generate-key", config_path],
            check=False,
            capture=True,
            env=env,
        )

        if result.returncode != 0:
            logger.error("Failed to generate GPG key: %s", result.stderr.strip())
            return None

        # Get the fingerprint of the newly created key by looking for the key name
        # Using key_name instead of email avoids returning an older key when
        # multiple keys share the same email
        list_result = run(
            ["gpg", "--list-keys", "--with-colons", key_name],
            check=False,
            capture=True,
        )

        if list_result.returncode != 0:
            logger.error("Failed to list GPG keys for %s", key_name)
            return None

        # Parse output to find fingerprint (fpr line)
        for line in list_result.stdout.split("\n"):
            if line.startswith("fpr:"):
                fingerprint = line.split(":")[9]
                logger.info("GPG key generated with fingerprint: %s", fingerprint)
                return GpgKeyResult(fingerprint=fingerprint, key_name=key_name)

        logger.error("Could not find fingerprint for newly generated key")
        return None

    finally:
        Path(config_path).unlink(missing_ok=True)


def add_gpg_key_to_github(fingerprint: str) -> bool:
    """Add GPG public key to GitHub using gh CLI."""
    if not command_exists("gh"):
        logger.warning("gh CLI not found, cannot add GPG key to GitHub")
        return False

    if not command_exists("gpg"):
        logger.warning("gpg not found, cannot export GPG key")
        return False

    if not _ensure_gh_authenticated("admin:gpg_key"):
        logger.warning("Cannot add GPG key without GitHub authentication")
        return False

    # Export the public key in armor format
    export_result = run(
        ["gpg", "--armor", "--export", fingerprint],
        check=False,
        capture=True,
    )

    if export_result.returncode != 0 or not export_result.stdout.strip():
        logger.error("Failed to export GPG public key")
        return False

    # Write to temp file for gh CLI
    with tempfile.NamedTemporaryFile(mode="w", suffix=".gpg", delete=False) as f:
        f.write(export_result.stdout)
        key_path = f.name

    try:
        logger.info("Adding GPG key to GitHub...")
        result = run(
            ["gh", "gpg-key", "add", key_path],
            check=False,
            capture=True,
        )

        if result.returncode != 0:
            error_output = f"{result.stdout}{result.stderr}".lower()
            if "already" in error_output:
                logger.info("GPG key already registered with GitHub")
                return True
            if "http 404" in error_output or "status 404" in error_output:
                if not _refresh_gh_scopes("admin:gpg_key"):
                    logger.warning("Failed to refresh GitHub auth scopes")
                    return False
                result = run(
                    ["gh", "gpg-key", "add", key_path],
                    check=False,
                    capture=True,
                )
                if result.returncode != 0:
                    error_output = f"{result.stdout}{result.stderr}".lower()
                    if "already" in error_output:
                        logger.info("GPG key already registered with GitHub")
                        return True
                    logger.warning("Failed to add GPG key to GitHub: %s", result.stderr.strip())
                    return False
                logger.info("GPG key added to GitHub")
                return True
            logger.warning("Failed to add GPG key to GitHub: %s", result.stderr.strip())
            return False

        logger.info("GPG key added to GitHub")
        return True

    finally:
        Path(key_path).unlink(missing_ok=True)


def setup_ssh(generate: bool = False) -> None:
    """Setup SSH key optionally."""
    if not generate:
        logger.info("SSH key generation skipped (use --generate-ssh-key to enable)")
        return

    if generate_ssh_key():
        key_title = generate_key_name()
        if add_ssh_key_to_github(title=key_title):
            fingerprint = get_ssh_key_fingerprint()
            if fingerprint:
                registry = KeyRegistry()
                registry.add(
                    KeyRecord(
                        key_type="ssh",
                        fingerprint=fingerprint,
                        title=key_title,
                        created_at=datetime.now().isoformat(),
                    )
                )
                logger.info("SSH key recorded in registry")


def setup_gpg(email: str, expiry_days: int = 90) -> None:
    """Setup GPG key with the given email."""
    gpg_result = generate_gpg_key(email, expiry_days=expiry_days)
    if gpg_result and add_gpg_key_to_github(gpg_result.fingerprint):
        registry = KeyRegistry()
        registry.add(
            KeyRecord(
                key_type="gpg",
                fingerprint=gpg_result.fingerprint,
                title=gpg_result.key_name,
                created_at=datetime.now().isoformat(),
            )
        )
        logger.info("GPG key recorded in registry")
