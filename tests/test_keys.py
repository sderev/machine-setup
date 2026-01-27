"""Tests for keys module."""

import json
from pathlib import Path

import machine_setup.keys as keys


class TestKeyRegistry:
    """Tests for the KeyRegistry class."""

    def test_sets_file_permissions(self, tmp_path: Path) -> None:
        """Sets 0o600 permissions on registry file."""
        registry_path = tmp_path / "machine-setup" / "keys.json"
        registry = keys.KeyRegistry(registry_path)

        record = keys.KeyRecord(
            key_type="ssh",
            fingerprint="ABC123",
            title="machine-setup-test-20260127",
            created_at="2026-01-27T10:00:00Z",
        )
        registry.add(record)

        # Check that permissions were set to 0o600
        assert (registry_path.stat().st_mode & 0o777) == 0o600

    def test_creates_registry_file(self, tmp_path: Path) -> None:
        """Creates registry file on first write."""
        registry_path = tmp_path / "machine-setup" / "keys.json"
        registry = keys.KeyRegistry(registry_path)

        record = keys.KeyRecord(
            key_type="ssh",
            fingerprint="ABC123",
            title="machine-setup-test-20260127",
            created_at="2026-01-27T10:00:00Z",
        )
        registry.add(record)

        assert registry_path.exists()
        data = json.loads(registry_path.read_text())
        assert len(data["keys"]) == 1
        assert data["keys"][0]["fingerprint"] == "ABC123"

    def test_loads_existing_registry(self, tmp_path: Path) -> None:
        """Loads existing registry from disk."""
        registry_path = tmp_path / "keys.json"
        registry_path.write_text(
            json.dumps(
                {
                    "keys": [
                        {
                            "key_type": "ssh",
                            "fingerprint": "XYZ789",
                            "title": "machine-setup-old-20260101",
                            "created_at": "2026-01-01T10:00:00Z",
                            "github_key_id": "12345",
                        }
                    ]
                }
            )
        )

        registry = keys.KeyRegistry(registry_path)

        assert len(registry.get_all()) == 1
        assert registry.get_all()[0].fingerprint == "XYZ789"

    def test_remove_key(self, tmp_path: Path) -> None:
        """Removes key by fingerprint."""
        registry_path = tmp_path / "keys.json"
        registry = keys.KeyRegistry(registry_path)

        record = keys.KeyRecord(
            key_type="ssh",
            fingerprint="TO_REMOVE",
            title="test-key",
            created_at="2026-01-27T10:00:00Z",
        )
        registry.add(record)

        assert registry.remove("TO_REMOVE") is True
        assert len(registry.get_all()) == 0

    def test_find_by_fingerprint(self, tmp_path: Path) -> None:
        """Finds key by fingerprint."""
        registry_path = tmp_path / "keys.json"
        registry = keys.KeyRegistry(registry_path)

        record = keys.KeyRecord(
            key_type="gpg",
            fingerprint="FINDME",
            title="test-key",
            created_at="2026-01-27T10:00:00Z",
        )
        registry.add(record)

        found = registry.find_by_fingerprint("FINDME")
        assert found is not None
        assert found.key_type == "gpg"


class TestGetRegistryPath:
    """Tests for get_registry_path function."""

    def test_uses_xdg_data_home(self, monkeypatch) -> None:
        """Uses XDG_DATA_HOME when set."""
        monkeypatch.setenv("XDG_DATA_HOME", "/custom/data")

        path = keys.get_registry_path()

        assert path == Path("/custom/data/machine-setup/keys.json")

    def test_defaults_to_local_share(self, monkeypatch, tmp_path: Path) -> None:
        """Defaults to ~/.local/share when XDG_DATA_HOME not set."""
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        monkeypatch.setattr(keys.Path, "home", lambda: tmp_path)

        path = keys.get_registry_path()

        assert path == tmp_path / ".local" / "share" / "machine-setup" / "keys.json"
