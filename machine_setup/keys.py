"""Key registry for machine-setup generated keys."""

import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path

logger = logging.getLogger("machine_setup")


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

    def get_all(self) -> list[KeyRecord]:
        """Get all key records."""
        return list(self._keys)

    def find_by_fingerprint(self, fingerprint: str) -> KeyRecord | None:
        """Find a key record by fingerprint."""
        for key in self._keys:
            if key.fingerprint == fingerprint:
                return key
        return None
