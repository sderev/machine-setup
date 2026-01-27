"""Tests for keys module."""

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from click.testing import CliRunner

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

    def test_remove_by_title(self, tmp_path: Path) -> None:
        """Removes key by title."""
        registry_path = tmp_path / "keys.json"
        registry = keys.KeyRegistry(registry_path)

        record = keys.KeyRecord(
            key_type="ssh",
            fingerprint="FINGERPRINT",
            title="machine-setup-test-20260127",
            created_at="2026-01-27T10:00:00Z",
        )
        registry.add(record)

        assert registry.remove_by_title("machine-setup-test-20260127") is True
        assert len(registry.get_all()) == 0

    def test_remove_by_title_returns_false_when_not_found(self, tmp_path: Path) -> None:
        """Returns False when title not found."""
        registry_path = tmp_path / "keys.json"
        registry = keys.KeyRegistry(registry_path)

        assert registry.remove_by_title("nonexistent") is False

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


class TestFilterMachineSetupKeys:
    """Tests for filter_machine_setup_keys function."""

    def test_filters_by_pattern(self) -> None:
        """Filters keys matching machine-setup-* pattern."""
        all_keys = [
            keys.GitHubKey("1", "machine-setup-host-20260127", "ssh", "2026-01-27"),
            keys.GitHubKey("2", "my-laptop", "ssh", "2026-01-20"),
            keys.GitHubKey("3", "machine-setup-other-20260101", "gpg", "2026-01-01"),
        ]

        filtered = keys.filter_machine_setup_keys(all_keys)

        assert len(filtered) == 2
        assert all(k.title.startswith("machine-setup-") for k in filtered)


class TestParseDuration:
    """Tests for parse_duration function."""

    def test_parses_days(self) -> None:
        """Parses 'Nd' format."""
        assert keys.parse_duration("30d") == 30
        assert keys.parse_duration("1d") == 1
        assert keys.parse_duration("365d") == 365

    def test_returns_none_for_invalid(self) -> None:
        """Returns None for invalid formats."""
        assert keys.parse_duration("30") is None
        assert keys.parse_duration("d30") is None
        assert keys.parse_duration("30days") is None
        assert keys.parse_duration("") is None


class TestIsKeyOlderThan:
    """Tests for is_key_older_than function."""

    def test_old_key(self) -> None:
        """Returns True for keys older than threshold."""
        old_date = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        key = keys.GitHubKey("1", "test", "ssh", old_date)

        assert keys.is_key_older_than(key, 30) is True

    def test_recent_key(self) -> None:
        """Returns False for keys newer than threshold."""
        recent_date = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        key = keys.GitHubKey("1", "test", "ssh", recent_date)

        assert keys.is_key_older_than(key, 30) is False

    def test_missing_created_at_logs_warning(self, caplog) -> None:
        """Logs warning when created_at is missing."""
        key = keys.GitHubKey("1", "test-key-no-date", "ssh", "")

        result = keys.is_key_older_than(key, 30)

        assert result is False
        assert "test-key-no-date" in caplog.text
        assert "no creation date" in caplog.text


class TestKeyListResult:
    """Tests for KeyListResult class."""

    def test_success_creates_result_with_keys(self) -> None:
        """success() creates a result with keys and no error."""
        key = keys.GitHubKey("1", "test", "ssh", "2026-01-27")
        result = keys.KeyListResult.success([key])

        assert result.keys == [key]
        assert result.error is None
        assert result.is_error is False

    def test_failure_creates_result_with_error(self) -> None:
        """failure() creates a result with error and empty keys."""
        result = keys.KeyListResult.failure("API error")

        assert result.keys == []
        assert result.error == "API error"
        assert result.is_error is True


class TestListGitHubSshKeys:
    """Tests for list_github_ssh_keys function."""

    def test_parses_json_output(self, monkeypatch) -> None:
        """Parses JSON output from gh CLI."""
        monkeypatch.setattr(keys, "command_exists", lambda cmd: True)

        def fake_run(cmd, *, check=True, capture=False, env=None):
            if "ssh-key" in cmd:
                output = json.dumps(
                    [
                        {
                            "id": 123,
                            "title": "machine-setup-test-20260127",
                            "createdAt": "2026-01-27T10:00:00Z",
                            "key": "ssh-ed25519 AAAA",
                        },
                        {
                            "id": 456,
                            "title": "other-key",
                            "createdAt": "2026-01-20T10:00:00Z",
                            "key": "ssh-rsa BBBB",
                        },
                    ]
                )
                return subprocess.CompletedProcess(cmd, 0, stdout=output, stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(keys, "run", fake_run)

        result = keys.list_github_ssh_keys()

        assert result.is_error is False
        assert len(result.keys) == 2
        assert result.keys[0].key_id == "123"
        assert result.keys[0].title == "machine-setup-test-20260127"

    def test_returns_error_on_api_failure(self, monkeypatch) -> None:
        """Returns error result when gh CLI fails."""
        monkeypatch.setattr(keys, "command_exists", lambda cmd: True)

        def fake_run(cmd, *, check=True, capture=False, env=None):
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="auth required")

        monkeypatch.setattr(keys, "run", fake_run)

        result = keys.list_github_ssh_keys()

        assert result.is_error is True
        assert "auth required" in result.error

    def test_returns_error_when_gh_not_found(self, monkeypatch) -> None:
        """Returns error result when gh CLI is not installed."""
        monkeypatch.setattr(keys, "command_exists", lambda cmd: False)

        result = keys.list_github_ssh_keys()

        assert result.is_error is True
        assert "gh CLI not found" in result.error


class TestKeysCliList:
    """Tests for keys list CLI command."""

    def test_lists_keys(self, monkeypatch) -> None:
        """Lists machine-setup keys from GitHub."""
        monkeypatch.setattr(keys, "command_exists", lambda cmd: True)

        def fake_run(cmd, *, check=True, capture=False, env=None):
            if "ssh-key" in cmd:
                output = json.dumps(
                    [
                        {
                            "id": 123,
                            "title": "machine-setup-test-20260127",
                            "createdAt": "2026-01-27T10:00:00Z",
                            "key": "ssh-ed25519 AAAA",
                        }
                    ]
                )
                return subprocess.CompletedProcess(cmd, 0, stdout=output, stderr="")
            if "gpg-key" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="[]", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(keys, "run", fake_run)

        runner = CliRunner()
        result = runner.invoke(keys.list_keys)

        assert result.exit_code == 0
        assert "machine-setup-test-20260127" in result.output
        assert "2026-01-27" in result.output

    def test_lists_gpg_keys_with_correct_naming(self, monkeypatch) -> None:
        """GPG keys with machine-setup-* name appear in list.

        Regression test: GPG keys must use generate_key_name() format
        (machine-setup-{hostname}-{date}) for Name-Real so they match KEY_PATTERN.
        """
        monkeypatch.setattr(keys, "command_exists", lambda cmd: True)

        def fake_run(cmd, *, check=True, capture=False, env=None):
            if "ssh-key" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="[]", stderr="")
            if "gpg-key" in cmd:
                output = json.dumps(
                    [
                        {
                            "id": 789,
                            "name": "machine-setup-myhost-20260127",
                            "createdAt": "2026-01-27T10:00:00Z",
                            "keyId": "ABCD1234",
                        }
                    ]
                )
                return subprocess.CompletedProcess(cmd, 0, stdout=output, stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(keys, "run", fake_run)

        runner = CliRunner()
        result = runner.invoke(keys.list_keys)

        assert result.exit_code == 0
        assert "GPG Keys:" in result.output
        assert "machine-setup-myhost-20260127" in result.output

    def test_no_keys_message(self, monkeypatch) -> None:
        """Shows message when no keys found."""
        monkeypatch.setattr(keys, "command_exists", lambda cmd: True)

        def fake_run(cmd, *, check=True, capture=False, env=None):
            return subprocess.CompletedProcess(cmd, 0, stdout="[]", stderr="")

        monkeypatch.setattr(keys, "run", fake_run)

        runner = CliRunner()
        result = runner.invoke(keys.list_keys)

        assert result.exit_code == 0
        assert "No machine-setup keys found" in result.output

    def test_shows_error_on_api_failure(self, monkeypatch) -> None:
        """Shows error message when GitHub API fails."""
        monkeypatch.setattr(keys, "command_exists", lambda cmd: True)

        def fake_run(cmd, *, check=True, capture=False, env=None):
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="auth required")

        monkeypatch.setattr(keys, "run", fake_run)

        runner = CliRunner()
        result = runner.invoke(keys.list_keys)

        assert result.exit_code == 1
        assert "Error:" in result.output
        assert "auth required" in result.output


class TestKeysCliPrune:
    """Tests for keys prune CLI command."""

    def test_prune_with_confirmation(self, monkeypatch) -> None:
        """Prunes keys after confirmation."""
        monkeypatch.setattr(keys, "command_exists", lambda cmd: True)

        deleted_ids = []

        def fake_run(cmd, *, check=True, capture=False, env=None):
            if "ssh-key" in cmd and "list" in cmd:
                output = json.dumps(
                    [
                        {
                            "id": 123,
                            "title": "machine-setup-test-20260127",
                            "createdAt": "2026-01-27T10:00:00Z",
                            "key": "ssh-ed25519 AAAA",
                        }
                    ]
                )
                return subprocess.CompletedProcess(cmd, 0, stdout=output, stderr="")
            if "gpg-key" in cmd and "list" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="[]", stderr="")
            if "ssh-key" in cmd and "delete" in cmd:
                deleted_ids.append(cmd[3])  # key ID is 4th argument
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(keys, "run", fake_run)

        runner = CliRunner()
        result = runner.invoke(keys.prune_keys, input="y\n")

        assert result.exit_code == 0
        assert "123" in deleted_ids
        assert "Deleted" in result.output

    def test_prune_older_than(self, monkeypatch) -> None:
        """Filters keys by age with --older-than."""
        monkeypatch.setattr(keys, "command_exists", lambda cmd: True)

        old_date = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        recent_date = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()

        deleted_ids = []

        def fake_run(cmd, *, check=True, capture=False, env=None):
            if "ssh-key" in cmd and "list" in cmd:
                output = json.dumps(
                    [
                        {
                            "id": 111,
                            "title": "machine-setup-old-20251127",
                            "createdAt": old_date,
                            "key": "ssh-ed25519 AAAA",
                        },
                        {
                            "id": 222,
                            "title": "machine-setup-recent-20260120",
                            "createdAt": recent_date,
                            "key": "ssh-ed25519 BBBB",
                        },
                    ]
                )
                return subprocess.CompletedProcess(cmd, 0, stdout=output, stderr="")
            if "gpg-key" in cmd and "list" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="[]", stderr="")
            if "ssh-key" in cmd and "delete" in cmd:
                deleted_ids.append(cmd[3])
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(keys, "run", fake_run)

        runner = CliRunner()
        result = runner.invoke(keys.prune_keys, ["--older-than", "30d", "--yes"])

        assert result.exit_code == 0
        assert "111" in deleted_ids
        assert "222" not in deleted_ids

    def test_prune_aborted(self, monkeypatch) -> None:
        """Aborts when user declines confirmation."""
        monkeypatch.setattr(keys, "command_exists", lambda cmd: True)

        def fake_run(cmd, *, check=True, capture=False, env=None):
            if "ssh-key" in cmd and "list" in cmd:
                output = json.dumps(
                    [
                        {
                            "id": 123,
                            "title": "machine-setup-test-20260127",
                            "createdAt": "2026-01-27T10:00:00Z",
                            "key": "ssh-ed25519 AAAA",
                        }
                    ]
                )
                return subprocess.CompletedProcess(cmd, 0, stdout=output, stderr="")
            if "gpg-key" in cmd and "list" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="[]", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(keys, "run", fake_run)

        runner = CliRunner()
        result = runner.invoke(keys.prune_keys, input="n\n")

        assert result.exit_code == 0
        assert "Aborted" in result.output

    def test_prune_cleans_registry_for_ssh_keys(self, monkeypatch, tmp_path: Path) -> None:
        """Removes SSH key entries from keys.json when keys are deleted."""
        monkeypatch.setattr(keys, "command_exists", lambda cmd: True)
        monkeypatch.setattr(keys, "get_registry_path", lambda: tmp_path / "keys.json")

        # Prepopulate registry with a key that will be deleted
        registry = keys.KeyRegistry()
        registry.add(
            keys.KeyRecord(
                key_type="ssh",
                fingerprint="SHA256:AAA",
                title="machine-setup-test-20260127",
                created_at="2026-01-27T10:00:00Z",
            )
        )

        def fake_run(cmd, *, check=True, capture=False, env=None):
            if "ssh-key" in cmd and "list" in cmd:
                output = json.dumps(
                    [
                        {
                            "id": 123,
                            "title": "machine-setup-test-20260127",
                            "createdAt": "2026-01-27T10:00:00Z",
                            "key": "ssh-ed25519 AAAA",
                        }
                    ]
                )
                return subprocess.CompletedProcess(cmd, 0, stdout=output, stderr="")
            if "gpg-key" in cmd and "list" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="[]", stderr="")
            if "ssh-key" in cmd and "delete" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(keys, "run", fake_run)

        runner = CliRunner()
        result = runner.invoke(keys.prune_keys, input="y\n")

        assert result.exit_code == 0

        # Verify registry was updated
        updated_registry = keys.KeyRegistry()
        assert len(updated_registry.get_all()) == 0

    def test_prune_cleans_registry_for_gpg_keys(self, monkeypatch, tmp_path: Path) -> None:
        """Removes GPG key entries from keys.json when keys are deleted."""
        monkeypatch.setattr(keys, "command_exists", lambda cmd: True)
        monkeypatch.setattr(keys, "get_registry_path", lambda: tmp_path / "keys.json")

        # Prepopulate registry with a key that will be deleted
        registry = keys.KeyRegistry()
        registry.add(
            keys.KeyRecord(
                key_type="gpg",
                fingerprint="ABCD1234",
                title="machine-setup-test-20260127",
                created_at="2026-01-27T10:00:00Z",
            )
        )

        def fake_run(cmd, *, check=True, capture=False, env=None):
            if "ssh-key" in cmd and "list" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="[]", stderr="")
            if "gpg-key" in cmd and "list" in cmd:
                output = json.dumps(
                    [
                        {
                            "id": 789,
                            "name": "machine-setup-test-20260127",
                            "createdAt": "2026-01-27T10:00:00Z",
                            "keyId": "ABCD1234",
                        }
                    ]
                )
                return subprocess.CompletedProcess(cmd, 0, stdout=output, stderr="")
            if "gpg-key" in cmd and "delete" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(keys, "run", fake_run)

        runner = CliRunner()
        result = runner.invoke(keys.prune_keys, input="y\n")

        assert result.exit_code == 0

        # Verify registry was updated
        updated_registry = keys.KeyRegistry()
        assert len(updated_registry.get_all()) == 0

    def test_prune_cleans_registry_for_gpg_keys_without_fingerprint(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        """Falls back to title-based removal when GPG key has no fingerprint."""
        monkeypatch.setattr(keys, "command_exists", lambda cmd: True)
        monkeypatch.setattr(keys, "get_registry_path", lambda: tmp_path / "keys.json")

        # Prepopulate registry with a key that will be deleted
        registry = keys.KeyRegistry()
        registry.add(
            keys.KeyRecord(
                key_type="gpg",
                fingerprint="LOCAL_FP",  # Registry has fingerprint
                title="machine-setup-test-20260127",
                created_at="2026-01-27T10:00:00Z",
            )
        )

        def fake_run(cmd, *, check=True, capture=False, env=None):
            if "ssh-key" in cmd and "list" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="[]", stderr="")
            if "gpg-key" in cmd and "list" in cmd:
                # GitHub returns key without keyId (fingerprint is None)
                output = json.dumps(
                    [
                        {
                            "id": 789,
                            "name": "machine-setup-test-20260127",
                            "createdAt": "2026-01-27T10:00:00Z",
                            # No "keyId" field -> fingerprint will be None
                        }
                    ]
                )
                return subprocess.CompletedProcess(cmd, 0, stdout=output, stderr="")
            if "gpg-key" in cmd and "delete" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(keys, "run", fake_run)

        runner = CliRunner()
        result = runner.invoke(keys.prune_keys, input="y\n")

        assert result.exit_code == 0

        # Verify registry was updated via title fallback
        updated_registry = keys.KeyRegistry()
        assert len(updated_registry.get_all()) == 0
