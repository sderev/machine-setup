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
