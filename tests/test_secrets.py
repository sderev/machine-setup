"""Tests for secrets module."""

import subprocess
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import machine_setup.secrets as secrets


class TestGenerateKeyName:
    """Tests for the generate_key_name function."""

    def test_format(self) -> None:
        """Key name follows format machine-setup-{hostname}-{YYYYMMDD}."""
        with patch.object(secrets.socket, "gethostname", return_value="testhost"):
            name = secrets.generate_key_name()

        today = datetime.now().strftime("%Y%m%d")
        assert name == f"machine-setup-testhost-{today}"

    def test_uses_actual_hostname(self) -> None:
        """Key name uses the actual hostname from socket."""
        with patch.object(secrets.socket, "gethostname", return_value="my-dev-box"):
            name = secrets.generate_key_name()

        assert "my-dev-box" in name


class TestGenerateSshKey:
    """Tests for SSH key generation."""

    def test_sets_private_key_permissions(self, monkeypatch, tmp_path: Path) -> None:
        """Sets 0o600 permissions on private key after generation."""
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir()

        monkeypatch.setattr(secrets.Path, "home", lambda *args, **kwargs: tmp_path)
        monkeypatch.setattr(secrets, "command_exists", lambda cmd: True)

        def fake_run(cmd: list[str], *, check: bool = True, capture: bool = False, env=None):
            if cmd[0] == "ssh-keygen" and "-t" in cmd:
                # Simulate ssh-keygen creating the key files
                private_key_path = ssh_dir / "id_ed25519"
                public_key_path = ssh_dir / "id_ed25519.pub"
                private_key_path.write_text("PRIVATE KEY")
                private_key_path.chmod(0o644)  # Simulate wrong permissions
                public_key_path.write_text("ssh-ed25519 AAAA\n")
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(secrets, "run", fake_run)

        assert secrets.generate_ssh_key() is True

        private_key_path = ssh_dir / "id_ed25519"
        # Check that permissions were set to 0o600
        assert (private_key_path.stat().st_mode & 0o777) == 0o600

    def test_restores_public_key(self, monkeypatch, tmp_path: Path) -> None:
        """Restores public key without prompting for a passphrase."""
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir()
        private_key_path = ssh_dir / "id_ed25519"
        private_key_path.write_text("dummy")

        monkeypatch.setattr(secrets.Path, "home", lambda *args, **kwargs: tmp_path)
        monkeypatch.setattr(secrets, "command_exists", lambda cmd: True)

        calls: list[list[str]] = []

        def fake_run(cmd: list[str], *, check: bool = True, capture: bool = False, env=None):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout="ssh-ed25519 AAAA", stderr="")

        monkeypatch.setattr(secrets, "run", fake_run)

        assert secrets.generate_ssh_key() is True

        public_key_path = ssh_dir / "id_ed25519.pub"
        assert public_key_path.read_text() == "ssh-ed25519 AAAA\n"
        assert calls == [["ssh-keygen", "-y", "-P", "", "-f", str(private_key_path)]]


class TestAddSshKeyToGitHub:
    """Tests for adding SSH keys to GitHub."""

    def test_authenticates(self, monkeypatch, tmp_path: Path) -> None:
        """Authenticates via device flow before registering key."""
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir()
        public_key_path = ssh_dir / "id_ed25519.pub"
        public_key_path.write_text("ssh-ed25519 AAAA\n")

        monkeypatch.setattr(secrets.Path, "home", lambda *args, **kwargs: tmp_path)
        monkeypatch.setattr(secrets, "command_exists", lambda cmd: True)

        calls: list[list[str]] = []

        def fake_run(cmd: list[str], *, check: bool = True, capture: bool = False, env=None):
            calls.append(cmd)
            if cmd[:3] == ["gh", "auth", "status"]:
                return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="not logged in")
            if cmd[:3] == ["gh", "auth", "login"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            if cmd[:3] == ["gh", "ssh-key", "add"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(secrets, "run", fake_run)

        with patch.object(secrets, "generate_key_name", return_value="machine-setup-test-20260127"):
            assert secrets.add_ssh_key_to_github() is True

        assert calls == [
            ["gh", "auth", "status", "--hostname", "github.com"],
            [
                "gh",
                "auth",
                "login",
                "--hostname",
                "github.com",
                "--git-protocol",
                "https",
                "--scopes",
                "admin:public_key",
            ],
            [
                "gh",
                "ssh-key",
                "add",
                str(public_key_path),
                "--title",
                "machine-setup-test-20260127",
            ],
        ]

    def test_refreshes_scopes_on_404(self, monkeypatch, tmp_path: Path) -> None:
        """Refreshes auth scopes when GitHub returns 404."""
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir()
        public_key_path = ssh_dir / "id_ed25519.pub"
        public_key_path.write_text("ssh-ed25519 AAAA\n")

        monkeypatch.setattr(secrets.Path, "home", lambda *args, **kwargs: tmp_path)
        monkeypatch.setattr(secrets, "command_exists", lambda cmd: True)

        calls: list[list[str]] = []
        add_calls = 0

        def fake_run(cmd: list[str], *, check: bool = True, capture: bool = False, env=None):
            nonlocal add_calls
            calls.append(cmd)
            if cmd[:3] == ["gh", "auth", "status"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            if cmd[:3] == ["gh", "ssh-key", "add"]:
                add_calls += 1
                if add_calls == 1:
                    return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="HTTP 404")
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            if cmd[:3] == ["gh", "auth", "refresh"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(secrets, "run", fake_run)

        with patch.object(secrets, "generate_key_name", return_value="machine-setup-test-20260127"):
            assert secrets.add_ssh_key_to_github() is True

        assert calls == [
            ["gh", "auth", "status", "--hostname", "github.com"],
            [
                "gh",
                "ssh-key",
                "add",
                str(public_key_path),
                "--title",
                "machine-setup-test-20260127",
            ],
            [
                "gh",
                "auth",
                "refresh",
                "--hostname",
                "github.com",
                "--scopes",
                "admin:public_key",
            ],
            [
                "gh",
                "ssh-key",
                "add",
                str(public_key_path),
                "--title",
                "machine-setup-test-20260127",
            ],
        ]

    def test_uses_custom_title(self, monkeypatch, tmp_path: Path) -> None:
        """Uses custom title when provided."""
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir()
        public_key_path = ssh_dir / "id_ed25519.pub"
        public_key_path.write_text("ssh-ed25519 AAAA\n")

        monkeypatch.setattr(secrets.Path, "home", lambda *args, **kwargs: tmp_path)
        monkeypatch.setattr(secrets, "command_exists", lambda cmd: True)

        calls: list[list[str]] = []

        def fake_run(cmd: list[str], *, check: bool = True, capture: bool = False, env=None):
            calls.append(cmd)
            if cmd[:3] == ["gh", "auth", "status"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            if cmd[:3] == ["gh", "ssh-key", "add"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(secrets, "run", fake_run)

        assert secrets.add_ssh_key_to_github(title="my-custom-title") is True

        # Check that custom title was used
        add_cmd = [c for c in calls if c[:3] == ["gh", "ssh-key", "add"]][0]
        assert "--title" in add_cmd
        title_idx = add_cmd.index("--title")
        assert add_cmd[title_idx + 1] == "my-custom-title"


class TestGenerateGpgKey:
    """Tests for GPG key generation."""

    def test_returns_none_when_gpg_not_found(self, monkeypatch) -> None:
        """Returns None when gpg is not installed."""
        monkeypatch.setattr(secrets, "command_exists", lambda cmd: False)

        result = secrets.generate_gpg_key("test@example.com")

        assert result is None

    def test_generates_key_and_returns_result(self, monkeypatch) -> None:
        """Generates key and returns GpgKeyResult on success."""
        monkeypatch.setattr(secrets, "command_exists", lambda cmd: True)

        calls: list[list[str]] = []

        def fake_run(cmd: list[str], *, check: bool = True, capture: bool = False, env=None):
            calls.append(cmd)
            if cmd[:3] == ["gpg", "--batch", "--generate-key"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            if cmd[:3] == ["gpg", "--list-keys", "--with-colons"]:
                # Simulate GPG colon-delimited output
                uid_line = (
                    "uid:u::::1706000000::HASH::machine-setup-test-20260127 <test@example.com>"
                )
                output = (
                    "pub:u:256:22:ABCDEF1234567890:1706000000::u:::scESC::ed25519:::0:\n"
                    "fpr:::::::::ABCDEF1234567890ABCDEF1234567890ABCDEF12::\n"
                    f"{uid_line}::::::::::0:\n"
                )
                return subprocess.CompletedProcess(cmd, 0, stdout=output, stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(secrets, "run", fake_run)

        with patch.object(secrets, "generate_key_name", return_value="machine-setup-test-20260127"):
            result = secrets.generate_gpg_key("test@example.com")

        assert result is not None
        assert result.fingerprint == "ABCDEF1234567890ABCDEF1234567890ABCDEF12"
        assert result.key_name == "machine-setup-test-20260127"
        # Verify lookup uses key_name not email
        list_cmd = [c for c in calls if c[:3] == ["gpg", "--list-keys", "--with-colons"]][0]
        assert list_cmd[3] == "machine-setup-test-20260127"

    def test_uses_expiry_days(self, monkeypatch, tmp_path: Path) -> None:
        """GPG config includes the specified expiry days."""
        monkeypatch.setattr(secrets, "command_exists", lambda cmd: True)

        config_content = None

        def fake_run(cmd: list[str], *, check: bool = True, capture: bool = False, env=None):
            nonlocal config_content
            if cmd[:3] == ["gpg", "--batch", "--generate-key"]:
                # Read the config file that was passed
                config_path = cmd[3]
                config_content = Path(config_path).read_text()
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            if cmd[:3] == ["gpg", "--list-keys", "--with-colons"]:
                output = "fpr:::::::::FINGERPRINT123::\n"
                return subprocess.CompletedProcess(cmd, 0, stdout=output, stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(secrets, "run", fake_run)

        with patch.object(secrets, "generate_key_name", return_value="machine-setup-test-20260127"):
            secrets.generate_gpg_key("test@example.com", expiry_days=30)

        assert config_content is not None
        assert "Expire-Date: 30d" in config_content

    def test_uses_key_name_for_name_real(self, monkeypatch, tmp_path: Path) -> None:
        """GPG config uses generate_key_name() for Name-Real field.

        This ensures GPG keys have titles matching KEY_PATTERN for list/prune.
        """
        monkeypatch.setattr(secrets, "command_exists", lambda cmd: True)

        config_content = None

        def fake_run(cmd: list[str], *, check: bool = True, capture: bool = False, env=None):
            nonlocal config_content
            if cmd[:3] == ["gpg", "--batch", "--generate-key"]:
                config_path = cmd[3]
                config_content = Path(config_path).read_text()
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            if cmd[:3] == ["gpg", "--list-keys", "--with-colons"]:
                output = "fpr:::::::::FINGERPRINT123::\n"
                return subprocess.CompletedProcess(cmd, 0, stdout=output, stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(secrets, "run", fake_run)

        with patch.object(
            secrets, "generate_key_name", return_value="machine-setup-myhost-20260127"
        ):
            secrets.generate_gpg_key("test@example.com")

        assert config_content is not None
        assert "Name-Real: machine-setup-myhost-20260127" in config_content


class TestAddGpgKeyToGitHub:
    """Tests for adding GPG keys to GitHub."""

    def test_exports_and_uploads_key(self, monkeypatch, tmp_path: Path) -> None:
        """Exports public key and uploads to GitHub."""
        monkeypatch.setattr(secrets, "command_exists", lambda cmd: True)

        calls: list[list[str]] = []

        def fake_run(cmd: list[str], *, check: bool = True, capture: bool = False, env=None):
            calls.append(cmd)
            if cmd[:3] == ["gh", "auth", "status"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            if cmd[:3] == ["gpg", "--armor", "--export"]:
                gpg_key = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nKEY\n-----END"
                return subprocess.CompletedProcess(cmd, 0, stdout=gpg_key, stderr="")
            if cmd[:3] == ["gh", "gpg-key", "add"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(secrets, "run", fake_run)

        assert secrets.add_gpg_key_to_github("FINGERPRINT123") is True

        # Check that export was called with fingerprint
        export_cmd = [c for c in calls if c[:3] == ["gpg", "--armor", "--export"]][0]
        assert "FINGERPRINT123" in export_cmd

        # Check that gh gpg-key add was called
        add_cmds = [c for c in calls if c[:3] == ["gh", "gpg-key", "add"]]
        assert len(add_cmds) == 1


class TestSetupSsh:
    """Tests for setup_ssh function."""

    def test_records_key_in_registry(self, monkeypatch, tmp_path: Path) -> None:
        """Records SSH key in registry after GitHub upload."""
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir()
        public_key_path = ssh_dir / "id_ed25519.pub"
        public_key_path.write_text("ssh-ed25519 AAAA\n")

        monkeypatch.setattr(secrets.Path, "home", lambda *args, **kwargs: tmp_path)
        monkeypatch.setattr(secrets, "command_exists", lambda cmd: True)

        registry_path = tmp_path / "registry" / "keys.json"

        class FakeKeyRegistry(secrets.KeyRegistry):
            def __init__(self, path=None):
                super().__init__(registry_path)

        monkeypatch.setattr(secrets, "KeyRegistry", FakeKeyRegistry)

        def fake_run(cmd: list[str], *, check: bool = True, capture: bool = False, env=None):
            if cmd[:3] == ["gh", "auth", "status"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            if cmd[:3] == ["gh", "ssh-key", "add"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            if cmd[:3] == ["ssh-keygen", "-l", "-f"]:
                return subprocess.CompletedProcess(
                    cmd, 0, stdout="256 SHA256:abc123 comment", stderr=""
                )
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(secrets, "run", fake_run)

        with (
            patch.object(secrets, "generate_key_name", return_value="machine-setup-test-20260127"),
            patch.object(secrets, "generate_ssh_key", return_value=True),
        ):
            secrets.setup_ssh(generate=True)

        # Verify key was recorded in registry
        registry = secrets.KeyRegistry(registry_path)
        keys = registry.get_all()
        assert len(keys) == 1
        assert keys[0].key_type == "ssh"
        assert keys[0].fingerprint == "SHA256:abc123"
        assert keys[0].title == "machine-setup-test-20260127"


class TestSetupGpg:
    """Tests for setup_gpg function."""

    def test_records_key_in_registry(self, monkeypatch, tmp_path: Path) -> None:
        """Records GPG key in registry after GitHub upload."""
        monkeypatch.setattr(secrets, "command_exists", lambda cmd: True)

        registry_path = tmp_path / "registry" / "keys.json"

        class FakeKeyRegistry(secrets.KeyRegistry):
            def __init__(self, path=None):
                super().__init__(registry_path)

        monkeypatch.setattr(secrets, "KeyRegistry", FakeKeyRegistry)

        def fake_run(cmd: list[str], *, check: bool = True, capture: bool = False, env=None):
            if cmd[:3] == ["gh", "auth", "status"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            if cmd[:3] == ["gpg", "--armor", "--export"]:
                gpg_key = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nKEY\n-----END"
                return subprocess.CompletedProcess(cmd, 0, stdout=gpg_key, stderr="")
            if cmd[:3] == ["gh", "gpg-key", "add"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(secrets, "run", fake_run)

        gpg_result = secrets.GpgKeyResult(
            fingerprint="FINGERPRINT123", key_name="machine-setup-test-20260127"
        )
        with patch.object(secrets, "generate_gpg_key", return_value=gpg_result):
            secrets.setup_gpg("test@example.com")

        # Verify key was recorded in registry
        registry = secrets.KeyRegistry(registry_path)
        keys = registry.get_all()
        assert len(keys) == 1
        assert keys[0].key_type == "gpg"
        assert keys[0].fingerprint == "FINGERPRINT123"
        assert keys[0].title == "machine-setup-test-20260127"
