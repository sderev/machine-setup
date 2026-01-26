"""Tests for packages module."""

import json
import os
from types import SimpleNamespace
from urllib import request as urllib_request

import pytest

from machine_setup import packages


class FakeResponse:
    """Simple response wrapper for urlopen mocks."""

    def __init__(self, data: bytes, status: int = 200) -> None:
        self._data = data
        self.status = status

    def read(self) -> bytes:
        return self._data

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def test_install_quarto_skips_when_installed(monkeypatch, caplog) -> None:
    """Skip Quarto install when command exists."""
    monkeypatch.setattr(packages, "command_exists", lambda cmd: cmd == "quarto")

    caplog.set_level("INFO", logger="machine_setup")
    packages.install_quarto()

    assert "Quarto already installed" in caplog.text


def test_install_quarto_downloads_and_cleans_tempfile(monkeypatch, caplog) -> None:
    """Install Quarto and remove the temporary package."""
    monkeypatch.setattr(packages, "command_exists", lambda _: False)

    api_payload = json.dumps(
        {
            "assets": [
                {
                    "name": "quarto-1.0.0-linux-amd64.deb",
                    "browser_download_url": "https://example.com/quarto.deb",
                }
            ]
        }
    ).encode("utf-8")
    responses = [
        FakeResponse(api_payload, status=200),
        FakeResponse(b"deb-contents", status=200),
    ]

    def fake_urlopen(req, timeout=0):
        if isinstance(req, urllib_request.Request):
            assert req.headers.get("User-agent") == "machine-setup/1.0"
        return responses.pop(0)

    monkeypatch.setattr(packages.urllib.request, "urlopen", fake_urlopen)

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        if cmd[:2] == ["dpkg", "--print-architecture"]:
            return SimpleNamespace(stdout="amd64\n")
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(packages, "run", fake_run)

    removed: list[str] = []
    real_remove = os.remove

    def fake_remove(path: str) -> None:
        removed.append(path)
        real_remove(path)

    monkeypatch.setattr(packages.os, "remove", fake_remove)

    caplog.set_level("INFO", logger="machine_setup")
    packages.install_quarto()

    assert any(cmd[:2] == ["dpkg", "--print-architecture"] for cmd in calls)
    assert any(cmd[idx : idx + 2] == ["dpkg", "-i"] for cmd in calls for idx in range(len(cmd) - 1))
    assert removed
    assert not os.path.exists(removed[0])
    assert "Quarto installation complete" in caplog.text


def test_install_quarto_rejects_unsupported_arch(monkeypatch) -> None:
    """Raise when architecture has no matching asset."""
    monkeypatch.setattr(packages, "command_exists", lambda _: False)

    api_payload = json.dumps({"assets": []}).encode("utf-8")
    monkeypatch.setattr(
        packages.urllib.request,
        "urlopen",
        lambda *args, **kwargs: FakeResponse(api_payload, status=200),
    )

    monkeypatch.setattr(
        packages,
        "run",
        lambda cmd, **kwargs: SimpleNamespace(stdout="riscv64\n"),
    )

    with pytest.raises(RuntimeError, match="Unsupported architecture"):
        packages.install_quarto()


def test_install_quarto_cleans_tempfile_on_failure(monkeypatch) -> None:
    """Remove the temporary package when installation fails."""
    monkeypatch.setattr(packages, "command_exists", lambda _: False)

    api_payload = json.dumps(
        {
            "assets": [
                {
                    "name": "quarto-1.0.0-linux-amd64.deb",
                    "browser_download_url": "https://example.com/quarto.deb",
                }
            ]
        }
    ).encode("utf-8")
    responses = [
        FakeResponse(api_payload, status=200),
        FakeResponse(b"deb-contents", status=200),
    ]

    monkeypatch.setattr(
        packages.urllib.request,
        "urlopen",
        lambda *args, **kwargs: responses.pop(0),
    )

    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["dpkg", "--print-architecture"]:
            return SimpleNamespace(stdout="amd64\n")
        raise packages.subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(packages, "run", fake_run)

    removed: list[str] = []
    real_remove = os.remove

    def fake_remove(path: str) -> None:
        removed.append(path)
        real_remove(path)

    monkeypatch.setattr(packages.os, "remove", fake_remove)

    with pytest.raises(packages.subprocess.CalledProcessError):
        packages.install_quarto()

    assert removed
    assert not os.path.exists(removed[0])


# --- npm tools tests ---


def test_install_npm_tools_uses_sudo_prefix(monkeypatch) -> None:
    """Global npm installs should use sudo when required."""
    calls: list[list[str]] = []

    monkeypatch.setattr(packages, "command_exists", lambda _: True)
    monkeypatch.setattr(packages, "sudo_prefix", lambda: ["sudo"])

    def fake_run(cmd, check=True, capture=False, env=None):
        calls.append(list(cmd))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(packages, "run", fake_run)

    packages.install_npm_tools(["tool"])

    assert calls == [["sudo", "npm", "install", "-g", "tool"]]


def test_install_npm_tools_skips_empty_list(monkeypatch, caplog) -> None:
    """Empty tool lists should short-circuit without running commands."""
    calls = {"command_exists": False, "run": False}

    def fake_command_exists(_):
        calls["command_exists"] = True
        return True

    def fake_run(cmd, check=True, capture=False, env=None):
        calls["run"] = True
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(packages, "command_exists", fake_command_exists)
    monkeypatch.setattr(packages, "run", fake_run)

    import logging

    caplog.set_level(logging.INFO, logger="machine_setup")
    packages.install_npm_tools([])

    assert calls == {"command_exists": False, "run": False}
    assert "No npm tools to install" in caplog.text


def test_install_npm_tools_skips_when_npm_missing(monkeypatch, caplog) -> None:
    """Missing npm should log a warning and skip installs."""
    calls = {"run": False}

    def fake_run(cmd, check=True, capture=False, env=None):
        calls["run"] = True
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(packages, "command_exists", lambda _: False)
    monkeypatch.setattr(packages, "run", fake_run)

    import logging

    caplog.set_level(logging.WARNING, logger="machine_setup")
    packages.install_npm_tools(["tool"])

    assert calls["run"] is False
    assert "npm not found; skipping npm tool installation" in caplog.text


def test_install_npm_tools_warns_on_failure(monkeypatch, caplog) -> None:
    """Failed npm installs should be surfaced in logs."""
    monkeypatch.setattr(packages, "command_exists", lambda _: True)
    monkeypatch.setattr(packages, "sudo_prefix", lambda: [])

    def fake_run(cmd, check=True, capture=False, env=None):
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(packages, "run", fake_run)

    import logging

    caplog.set_level(logging.WARNING, logger="machine_setup")
    packages.install_npm_tools(["tool"])

    assert "npm tool install failed for tool" in caplog.text
