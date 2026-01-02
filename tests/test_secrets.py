"""Tests for secrets module."""

import subprocess
from pathlib import Path

import machine_setup.secrets as secrets


def test_generate_ssh_key_restores_public_key(monkeypatch, tmp_path: Path) -> None:
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


def test_add_ssh_key_to_github_authenticates(monkeypatch, tmp_path: Path) -> None:
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

    assert secrets.add_ssh_key_to_github() is True

    assert calls == [
        ["gh", "auth", "status", "--hostname", "github.com"],
        ["gh", "auth", "login", "--hostname", "github.com", "--git-protocol", "https"],
        ["gh", "ssh-key", "add", str(public_key_path), "--title", "machine-setup"],
    ]
