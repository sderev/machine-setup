"""Proton Pass CLI integration for secrets."""

import logging
from pathlib import Path

from machine_setup.utils import command_exists, run

logger = logging.getLogger("machine_setup")


def is_proton_pass_available() -> bool:
    """Check if Proton Pass CLI is installed and authenticated."""
    if not command_exists("proton-pass"):
        return False

    result = run(["proton-pass", "status"], check=False, capture=True)
    return result.returncode == 0


def get_secret(uri: str) -> str | None:
    """
    Retrieve a secret from Proton Pass.

    URI format: pass://vault/item/field
    """
    if not is_proton_pass_available():
        logger.warning("Proton Pass not available, skipping secret: %s", uri)
        return None

    result = run(["proton-pass", "get", uri], check=False, capture=True)
    if result.returncode != 0:
        logger.warning("Failed to retrieve secret: %s", uri)
        return None

    return result.stdout.strip()


def setup_ssh_key(key_name: str = "id_ed25519") -> bool:
    """Retrieve and setup SSH key from Proton Pass."""
    ssh_dir = Path.home() / ".ssh"
    ssh_dir.mkdir(mode=0o700, exist_ok=True)
    ssh_dir.chmod(0o700)

    private_key_path = ssh_dir / key_name
    public_key_path = ssh_dir / f"{key_name}.pub"

    if private_key_path.exists() and public_key_path.exists():
        logger.info("SSH key already exists at %s", private_key_path)
        return True

    private_key = get_secret(f"pass://SSH Keys/{key_name}/private_key")
    public_key = get_secret(f"pass://SSH Keys/{key_name}/public_key")

    if not private_key or not public_key:
        logger.warning("Could not retrieve SSH key from Proton Pass")
        return False

    private_key_path.write_text(private_key)
    private_key_path.chmod(0o600)

    public_key_path.write_text(public_key)
    public_key_path.chmod(0o644)

    logger.info("SSH key setup complete")
    return True


def setup_secrets(skip: bool = False) -> None:
    """Setup all secrets from Proton Pass."""
    if skip:
        logger.info("Skipping secrets setup (--skip-secrets)")
        return

    if not is_proton_pass_available():
        logger.warning(
            "Proton Pass CLI not available or not authenticated. "
            "Run 'proton-pass login' manually to enable secrets sync."
        )
        return

    setup_ssh_key("id_ed25519")
