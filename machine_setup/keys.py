"""Key registry and management for machine-setup generated keys."""

import json
import logging
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import click

from machine_setup.utils import command_exists, run

logger = logging.getLogger("machine_setup")

# Pattern for keys managed by machine-setup
KEY_PATTERN = re.compile(r"^machine-setup-")


@dataclass
class KeyListResult:
    """Result of listing keys from GitHub.

    Either keys is populated (success) or error is set (failure).
    """

    keys: list["GitHubKey"]
    error: str | None = None

    @property
    def is_error(self) -> bool:
        """Check if this result represents an error."""
        return self.error is not None

    @classmethod
    def success(cls, keys: list["GitHubKey"]) -> "KeyListResult":
        """Create a successful result."""
        return cls(keys=keys, error=None)

    @classmethod
    def failure(cls, error: str) -> "KeyListResult":
        """Create a failure result."""
        return cls(keys=[], error=error)


def get_registry_path() -> Path:
    """Get the XDG-compliant path for the key registry."""
    xdg_data_home = os.environ.get("XDG_DATA_HOME", "")
    base = Path(xdg_data_home) if xdg_data_home else Path.home() / ".local" / "share"
    return base / "machine-setup" / "keys.json"


@dataclass
class KeyRecord:
    """Record of a machine-setup managed key."""

    key_type: str  # "ssh" or "gpg"
    fingerprint: str  # SSH key fingerprint or GPG fingerprint
    title: str  # Key name/title on GitHub
    created_at: str  # ISO format date
    github_key_id: str | None = None  # GitHub's key ID if known


class KeyRegistry:
    """Registry for tracking machine-setup managed keys."""

    def __init__(self, path: Path | None = None):
        self.path = path or get_registry_path()
        self._keys: list[KeyRecord] = []
        self._load()

    def _load(self) -> None:
        """Load registry from disk."""
        if not self.path.exists():
            self._keys = []
            return

        try:
            data = json.loads(self.path.read_text())
            self._keys = [KeyRecord(**k) for k in data.get("keys", [])]
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning("Failed to load key registry: %s", e)
            self._keys = []

    def _save(self) -> None:
        """Save registry to disk."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"keys": [asdict(k) for k in self._keys]}
        self.path.write_text(json.dumps(data, indent=2))
        self.path.chmod(0o600)

    def add(self, record: KeyRecord) -> None:
        """Add a key record to the registry."""
        self._keys.append(record)
        self._save()

    def remove(self, fingerprint: str) -> bool:
        """Remove a key record by fingerprint."""
        before = len(self._keys)
        self._keys = [k for k in self._keys if k.fingerprint != fingerprint]
        if len(self._keys) < before:
            self._save()
            return True
        return False

    def remove_by_title(self, title: str) -> bool:
        """Remove a key record by title."""
        before = len(self._keys)
        self._keys = [k for k in self._keys if k.title != title]
        if len(self._keys) < before:
            self._save()
            return True
        return False

    def get_all(self) -> list[KeyRecord]:
        """Get all key records."""
        return list(self._keys)

    def find_by_fingerprint(self, fingerprint: str) -> KeyRecord | None:
        """Find a key record by fingerprint."""
        for key in self._keys:
            if key.fingerprint == fingerprint:
                return key
        return None


@dataclass
class GitHubKey:
    """Representation of a GitHub SSH or GPG key."""

    key_id: str
    title: str
    key_type: str  # "ssh" or "gpg"
    created_at: str
    fingerprint: str | None = None  # Only for GPG keys


def list_github_ssh_keys() -> KeyListResult:
    """List SSH keys from GitHub.

    Returns a KeyListResult that either contains the keys or an error message.
    """
    if not command_exists("gh"):
        return KeyListResult.failure("gh CLI not found")

    result = run(
        ["gh", "ssh-key", "list", "--json", "id,title,createdAt,key"],
        check=False,
        capture=True,
    )

    if result.returncode != 0:
        error_msg = result.stderr.strip() or "Unknown error"
        return KeyListResult.failure(f"Failed to list SSH keys: {error_msg}")

    try:
        keys_data = json.loads(result.stdout)
        keys = [
            GitHubKey(
                key_id=str(k["id"]),
                title=k.get("title", ""),
                key_type="ssh",
                created_at=k.get("createdAt", ""),
            )
            for k in keys_data
        ]
        return KeyListResult.success(keys)
    except (json.JSONDecodeError, KeyError) as e:
        return KeyListResult.failure(f"Failed to parse SSH keys: {e}")


def list_github_gpg_keys() -> KeyListResult:
    """List GPG keys from GitHub.

    Returns a KeyListResult that either contains the keys or an error message.
    """
    if not command_exists("gh"):
        return KeyListResult.failure("gh CLI not found")

    result = run(
        ["gh", "gpg-key", "list", "--json", "id,name,createdAt,keyId"],
        check=False,
        capture=True,
    )

    if result.returncode != 0:
        error_msg = result.stderr.strip() or "Unknown error"
        return KeyListResult.failure(f"Failed to list GPG keys: {error_msg}")

    try:
        keys_data = json.loads(result.stdout)
        keys = [
            GitHubKey(
                key_id=str(k["id"]),
                title=k.get("name", ""),
                key_type="gpg",
                created_at=k.get("createdAt", ""),
                fingerprint=k.get("keyId"),
            )
            for k in keys_data
        ]
        return KeyListResult.success(keys)
    except (json.JSONDecodeError, KeyError) as e:
        return KeyListResult.failure(f"Failed to parse GPG keys: {e}")


def delete_github_ssh_key(key_id: str) -> bool:
    """Delete an SSH key from GitHub."""
    if not command_exists("gh"):
        logger.warning("gh CLI not found")
        return False

    result = run(
        ["gh", "ssh-key", "delete", key_id, "--yes"],
        check=False,
        capture=True,
    )

    if result.returncode != 0:
        logger.warning("Failed to delete SSH key %s: %s", key_id, result.stderr.strip())
        return False

    return True


def delete_github_gpg_key(key_id: str) -> bool:
    """Delete a GPG key from GitHub."""
    if not command_exists("gh"):
        logger.warning("gh CLI not found")
        return False

    result = run(
        ["gh", "gpg-key", "delete", key_id, "--yes"],
        check=False,
        capture=True,
    )

    if result.returncode != 0:
        logger.warning("Failed to delete GPG key %s: %s", key_id, result.stderr.strip())
        return False

    return True


def filter_machine_setup_keys(keys: list[GitHubKey]) -> list[GitHubKey]:
    """Filter keys to only include machine-setup managed keys."""
    return [k for k in keys if KEY_PATTERN.match(k.title)]


def parse_duration(duration_str: str) -> int | None:
    """Parse a duration string like '30d' into days.

    Returns None if parsing fails.
    """
    match = re.match(r"^(\d+)d$", duration_str.strip())
    if match:
        return int(match.group(1))
    return None


def is_key_older_than(key: GitHubKey, days: int) -> bool:
    """Check if a key is older than the specified number of days."""
    if not key.created_at:
        logger.warning("Key '%s' has no creation date, skipping age check", key.title)
        return False

    try:
        # GitHub returns ISO format dates like "2025-01-27T10:30:00Z"
        created = datetime.fromisoformat(key.created_at.replace("Z", "+00:00"))
        now = datetime.now(created.tzinfo)
        age_days = (now - created).days
        return age_days > days
    except ValueError:
        logger.warning("Could not parse date for key %s: %s", key.title, key.created_at)
        return False


# CLI Commands


@click.group(name="keys")
def keys_cli() -> None:
    """Manage machine-setup generated keys on GitHub."""


@keys_cli.command(name="list")
def list_keys() -> None:
    """List all machine-setup-* keys on GitHub."""
    if not command_exists("gh"):
        click.echo("Error: gh CLI not found", err=True)
        raise SystemExit(1)

    ssh_result = list_github_ssh_keys()
    gpg_result = list_github_gpg_keys()

    # Report errors
    errors = []
    if ssh_result.is_error:
        errors.append(f"SSH: {ssh_result.error}")
    if gpg_result.is_error:
        errors.append(f"GPG: {gpg_result.error}")

    if errors:
        for error in errors:
            click.echo(f"Error: {error}", err=True)
        raise SystemExit(1)

    ssh_keys = filter_machine_setup_keys(ssh_result.keys)
    gpg_keys = filter_machine_setup_keys(gpg_result.keys)

    if not ssh_keys and not gpg_keys:
        click.echo("No machine-setup keys found on GitHub.")
        return

    if ssh_keys:
        click.echo("SSH Keys:")
        for key in ssh_keys:
            created = key.created_at[:10] if key.created_at else "unknown"
            click.echo(f"  [{key.key_id}] {key.title} (created: {created})")

    if gpg_keys:
        if ssh_keys:
            click.echo()
        click.echo("GPG Keys:")
        for key in gpg_keys:
            created = key.created_at[:10] if key.created_at else "unknown"
            fingerprint = f" fingerprint={key.fingerprint}" if key.fingerprint else ""
            click.echo(f"  [{key.key_id}] {key.title} (created: {created}){fingerprint}")


@keys_cli.command(name="prune")
@click.option(
    "--older-than",
    type=str,
    default=None,
    help="Only delete keys older than N days (e.g., '30d')",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    help="Skip confirmation prompt",
)
def prune_keys(older_than: str | None, yes: bool) -> None:
    """Interactively delete machine-setup-* keys from GitHub."""
    if not command_exists("gh"):
        click.echo("Error: gh CLI not found", err=True)
        raise SystemExit(1)

    ssh_result = list_github_ssh_keys()
    gpg_result = list_github_gpg_keys()

    # Report errors
    errors = []
    if ssh_result.is_error:
        errors.append(f"SSH: {ssh_result.error}")
    if gpg_result.is_error:
        errors.append(f"GPG: {gpg_result.error}")

    if errors:
        for error in errors:
            click.echo(f"Error: {error}", err=True)
        raise SystemExit(1)

    ssh_keys = filter_machine_setup_keys(ssh_result.keys)
    gpg_keys = filter_machine_setup_keys(gpg_result.keys)

    all_keys = ssh_keys + gpg_keys

    if not all_keys:
        click.echo("No machine-setup keys found to prune.")
        return

    # Filter by age if specified
    if older_than:
        days = parse_duration(older_than)
        if days is None:
            click.echo(
                f"Error: Invalid duration format '{older_than}'. Use format like '30d'.", err=True
            )
            raise SystemExit(1)

        all_keys = [k for k in all_keys if is_key_older_than(k, days)]
        if not all_keys:
            click.echo(f"No machine-setup keys older than {days} days found.")
            return

    # Show keys to be deleted
    click.echo("Keys to be deleted:")
    for key in all_keys:
        created = key.created_at[:10] if key.created_at else "unknown"
        click.echo(f"  [{key.key_type.upper()}] {key.title} (created: {created})")

    click.echo()

    # Confirm deletion
    if not yes and not click.confirm(f"Delete {len(all_keys)} key(s)?"):
        click.echo("Aborted.")
        return

    # Load registry for cleanup
    registry = KeyRegistry()

    # Delete keys
    deleted = 0
    for key in all_keys:
        if key.key_type == "ssh":
            if delete_github_ssh_key(key.key_id):
                click.echo(f"Deleted SSH key: {key.title}")
                registry.remove_by_title(key.title)
                deleted += 1
            else:
                click.echo(f"Failed to delete SSH key: {key.title}", err=True)
        else:
            if delete_github_gpg_key(key.key_id):
                click.echo(f"Deleted GPG key: {key.title}")
                # Remove from registry by fingerprint, or fall back to title
                if key.fingerprint:
                    registry.remove(key.fingerprint)
                else:
                    registry.remove_by_title(key.title)
                deleted += 1
            else:
                click.echo(f"Failed to delete GPG key: {key.title}", err=True)

    click.echo(f"\nDeleted {deleted}/{len(all_keys)} key(s).")
