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
