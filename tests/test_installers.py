"""Tests for installers module."""

import io
import json
import logging
import os
import shutil
import subprocess
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib import request as urllib_request

import pytest

from machine_setup import installers


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


# --- Quarto tests ---


def test_install_quarto_skips_when_installed(monkeypatch, caplog) -> None:
    """Skip Quarto install when command exists."""
    monkeypatch.setattr(installers, "command_exists", lambda cmd: cmd == "quarto")

    caplog.set_level("INFO", logger="machine_setup")
    installers.install_quarto()

    assert "Quarto already installed" in caplog.text


def test_install_quarto_downloads_and_cleans_tempfile(monkeypatch, caplog) -> None:
    """Install Quarto and remove the temporary package."""
    monkeypatch.setattr(installers, "command_exists", lambda _: False)

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

    monkeypatch.setattr(installers.urllib.request, "urlopen", fake_urlopen)

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        if cmd[:2] == ["dpkg", "--print-architecture"]:
            return SimpleNamespace(stdout="amd64\n")
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(installers, "run", fake_run)

    removed: list[str] = []
    real_remove = os.remove

    def fake_remove(path: str) -> None:
        removed.append(path)
        real_remove(path)

    monkeypatch.setattr(installers.os, "remove", fake_remove)

    caplog.set_level("INFO", logger="machine_setup")
    installers.install_quarto()

    assert any(cmd[:2] == ["dpkg", "--print-architecture"] for cmd in calls)
    assert any(cmd[idx : idx + 2] == ["dpkg", "-i"] for cmd in calls for idx in range(len(cmd) - 1))
    assert removed
    assert not os.path.exists(removed[0])
    assert "Quarto installation complete" in caplog.text


def test_install_quarto_rejects_unsupported_arch(monkeypatch) -> None:
    """Raise when architecture has no matching asset."""
    monkeypatch.setattr(installers, "command_exists", lambda _: False)

    api_payload = json.dumps({"assets": []}).encode("utf-8")
    monkeypatch.setattr(
        installers.urllib.request,
        "urlopen",
        lambda *args, **kwargs: FakeResponse(api_payload, status=200),
    )

    monkeypatch.setattr(
        installers,
        "run",
        lambda cmd, **kwargs: SimpleNamespace(stdout="riscv64\n"),
    )

    with pytest.raises(RuntimeError, match="Unsupported architecture"):
        installers.install_quarto()


def test_install_quarto_cleans_tempfile_on_failure(monkeypatch) -> None:
    """Remove the temporary package when installation fails."""
    monkeypatch.setattr(installers, "command_exists", lambda _: False)

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
        installers.urllib.request,
        "urlopen",
        lambda *args, **kwargs: responses.pop(0),
    )

    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["dpkg", "--print-architecture"]:
            return SimpleNamespace(stdout="amd64\n")
        raise installers.subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(installers, "run", fake_run)

    removed: list[str] = []
    real_remove = os.remove

    def fake_remove(path: str) -> None:
        removed.append(path)
        real_remove(path)

    monkeypatch.setattr(installers.os, "remove", fake_remove)

    with pytest.raises(installers.subprocess.CalledProcessError):
        installers.install_quarto()

    assert removed
    assert not os.path.exists(removed[0])


# --- npm tools tests ---


def test_install_npm_tools_uses_sudo_prefix(monkeypatch) -> None:
    """Global npm installs should use sudo when required."""
    calls: list[list[str]] = []

    monkeypatch.setattr(installers, "command_exists", lambda _: True)
    monkeypatch.setattr(installers, "sudo_prefix", lambda: ["sudo"])

    def fake_run(cmd, check=True, capture=False, env=None):
        calls.append(list(cmd))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(installers, "run", fake_run)

    installers.install_npm_tools(["tool"])

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

    monkeypatch.setattr(installers, "command_exists", fake_command_exists)
    monkeypatch.setattr(installers, "run", fake_run)

    caplog.set_level(logging.INFO, logger="machine_setup")
    installers.install_npm_tools([])

    assert calls == {"command_exists": False, "run": False}
    assert "No npm tools to install" in caplog.text


def test_install_npm_tools_skips_when_npm_missing(monkeypatch, caplog) -> None:
    """Missing npm should log a warning and skip installs."""
    calls = {"run": False}

    def fake_run(cmd, check=True, capture=False, env=None):
        calls["run"] = True
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(installers, "command_exists", lambda _: False)
    monkeypatch.setattr(installers, "run", fake_run)

    caplog.set_level(logging.WARNING, logger="machine_setup")
    installers.install_npm_tools(["tool"])

    assert calls["run"] is False
    assert "npm not found; skipping npm tool installation" in caplog.text


def test_install_npm_tools_warns_on_failure(monkeypatch, caplog) -> None:
    """Failed npm installs should be surfaced in logs."""
    monkeypatch.setattr(installers, "command_exists", lambda _: True)
    monkeypatch.setattr(installers, "sudo_prefix", lambda: [])

    def fake_run(cmd, check=True, capture=False, env=None):
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(installers, "run", fake_run)

    caplog.set_level(logging.WARNING, logger="machine_setup")
    installers.install_npm_tools(["tool"])

    assert "npm tool install failed for tool" in caplog.text


# --- uv tools tests ---


def test_install_uv_tools_empty_list(caplog) -> None:
    """Log info message when no tools to install."""
    caplog.set_level(logging.INFO, logger="machine_setup")
    installers.install_uv_tools([])

    assert "No uv tools to install" in caplog.text


def test_install_uv_tools_skips_when_uv_missing(monkeypatch, caplog) -> None:
    """Skip installation when uv not found."""
    monkeypatch.setattr(installers, "command_exists", lambda _: False)

    caplog.set_level(logging.WARNING, logger="machine_setup")
    installers.install_uv_tools(["some-tool"])

    assert "uv not found" in caplog.text


def test_install_uv_tools_installs_tools(monkeypatch, caplog) -> None:
    """Install each tool via uv tool install."""
    calls: list[list[str]] = []

    monkeypatch.setattr(installers, "command_exists", lambda _: True)
    monkeypatch.setattr(
        installers,
        "run",
        lambda cmd, check: calls.append(list(cmd)) or SimpleNamespace(returncode=0),
    )

    caplog.set_level(logging.INFO, logger="machine_setup")
    installers.install_uv_tools(["tool-a", "tool-b"])

    assert calls[0] == ["uv", "tool", "install", "tool-a"]
    assert calls[1] == ["uv", "tool", "install", "tool-b"]
    assert "Installing tool-a via uv tool" in caplog.text
    assert "Installing tool-b via uv tool" in caplog.text


def test_install_uv_tools_handles_failure(monkeypatch, caplog) -> None:
    """Log warning when tool installation fails."""
    monkeypatch.setattr(installers, "command_exists", lambda _: True)
    monkeypatch.setattr(
        installers,
        "run",
        lambda cmd, check: SimpleNamespace(returncode=1),
    )

    caplog.set_level(logging.WARNING, logger="machine_setup")
    installers.install_uv_tools(["failing-tool"])

    assert "uv tool install failed for failing-tool" in caplog.text


# --- Claude Code tests ---


def test_install_claude_code_skips_when_already_installed(monkeypatch, caplog) -> None:
    """Skip installation when claude command already exists."""
    monkeypatch.setattr(installers, "command_exists", lambda cmd: cmd == "claude")

    caplog.set_level("INFO", logger="machine_setup")
    installers.install_claude_code()

    assert "Claude Code already installed" in caplog.text


def test_install_claude_code_runs_installer(monkeypatch, caplog) -> None:
    """Run curl and bash to install Claude Code."""
    calls: list[list[str]] = []
    bash_inputs: list[str] = []

    monkeypatch.setattr(installers, "command_exists", lambda _: False)

    def fake_subprocess_run(cmd, **kwargs):
        if cmd[0] == "curl":
            calls.append(list(cmd))
            return SimpleNamespace(returncode=0, stdout="fake installer script")
        elif cmd[0] == "bash":
            calls.append(["bash"])
            bash_inputs.append(kwargs.get("input", ""))
            return SimpleNamespace(returncode=0)
        raise ValueError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)

    caplog.set_level("INFO", logger="machine_setup")
    installers.install_claude_code()

    assert calls[0] == ["curl", "-fsSL", "--max-time", "30", installers.CLAUDE_INSTALL_URL]
    assert calls[1] == ["bash"]
    assert bash_inputs[0] == "fake installer script"
    assert "Claude Code installed successfully" in caplog.text
    assert "You may need to restart your shell" in caplog.text


def test_install_claude_code_handles_failure(monkeypatch, caplog) -> None:
    """Log warning when installation fails."""
    monkeypatch.setattr(installers, "command_exists", lambda _: False)

    def fake_subprocess_run(cmd, **kwargs):
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)

    caplog.set_level(logging.WARNING, logger="machine_setup")
    installers.install_claude_code()

    assert "Failed to install Claude Code" in caplog.text


def test_install_claude_code_handles_curl_failure(monkeypatch, caplog) -> None:
    """Log warning when curl fails to fetch installer."""
    monkeypatch.setattr(installers, "command_exists", lambda _: False)

    def fake_subprocess_run(cmd, **kwargs):
        if cmd[0] == "curl":
            raise subprocess.CalledProcessError(22, cmd)  # HTTP error
        raise ValueError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)

    caplog.set_level(logging.WARNING, logger="machine_setup")
    installers.install_claude_code()

    assert "Failed to install Claude Code" in caplog.text


def test_install_claude_code_handles_bash_failure(monkeypatch, caplog) -> None:
    """Log warning when bash installer script fails."""
    monkeypatch.setattr(installers, "command_exists", lambda _: False)

    def fake_subprocess_run(cmd, **kwargs):
        if cmd[0] == "curl":
            return SimpleNamespace(returncode=0, stdout="fake installer script")
        elif cmd[0] == "bash":
            raise subprocess.CalledProcessError(1, cmd)
        raise ValueError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)

    caplog.set_level(logging.WARNING, logger="machine_setup")
    installers.install_claude_code()

    assert "Failed to install Claude Code" in caplog.text


def test_install_claude_code_handles_curl_timeout(monkeypatch, caplog) -> None:
    """Log warning when curl times out (exit code 28)."""
    monkeypatch.setattr(installers, "command_exists", lambda _: False)

    def fake_subprocess_run(cmd, **kwargs):
        if cmd[0] == "curl":
            raise subprocess.CalledProcessError(28, cmd)  # curl timeout exit code
        raise ValueError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)

    caplog.set_level(logging.WARNING, logger="machine_setup")
    installers.install_claude_code()

    assert "Failed to install Claude Code" in caplog.text


# --- SCC tests ---


def test_install_scc_skips_when_installed(monkeypatch, caplog) -> None:
    """Skip SCC install when command exists."""
    monkeypatch.setattr(installers, "command_exists", lambda cmd: cmd == "scc")

    caplog.set_level("INFO", logger="machine_setup")
    installers.install_scc()

    assert "SCC already installed" in caplog.text


def test_install_scc_skips_when_go_missing(monkeypatch, caplog) -> None:
    """Skip SCC install when go is not available."""
    monkeypatch.setattr(installers, "command_exists", lambda cmd: False)

    caplog.set_level(logging.WARNING, logger="machine_setup")
    installers.install_scc()

    assert "Go not found; skipping SCC installation" in caplog.text


def test_install_scc_installs_via_go(monkeypatch, caplog) -> None:
    """Install SCC via go install."""
    calls: list[list[str]] = []

    def fake_command_exists(cmd):
        return cmd == "go"

    monkeypatch.setattr(installers, "command_exists", fake_command_exists)

    def fake_run(cmd, check=False, capture=False, env=None):
        calls.append(list(cmd))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(installers, "run", fake_run)

    caplog.set_level(logging.INFO, logger="machine_setup")
    installers.install_scc()

    assert calls == [["go", "install", "github.com/boyter/scc/v3@latest"]]
    assert "Installing SCC via go install" in caplog.text
    assert "SCC installed successfully" in caplog.text


def test_install_scc_handles_failure(monkeypatch, caplog) -> None:
    """Log warning when SCC installation fails."""

    def fake_command_exists(cmd):
        return cmd == "go"

    monkeypatch.setattr(installers, "command_exists", fake_command_exists)

    def fake_run(cmd, check=False, capture=False, env=None):
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(installers, "run", fake_run)

    caplog.set_level(logging.WARNING, logger="machine_setup")
    installers.install_scc()

    assert "Failed to install SCC" in caplog.text


# --- Fira Code tests ---


def _make_fira_code_zip() -> bytes:
    """Build an in-memory zip with fake TTF files in a ttf/ subdirectory."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name in installers.FIRA_CODE_FONT_NAMES:
            zf.writestr(f"ttf/{name}", b"fake-ttf-data")
    return buf.getvalue()


def _fira_code_api_payload() -> bytes:
    return json.dumps(
        {
            "assets": [
                {
                    "name": "Fira_Code_v6.2.zip",
                    "browser_download_url": "https://example.com/Fira_Code.zip",
                }
            ]
        }
    ).encode("utf-8")


def test_install_fira_code_skips_when_already_installed(tmp_path, monkeypatch, caplog) -> None:
    """Skip when FiraCode-Retina.ttf already exists in target."""
    fonts_dir = tmp_path / ".local" / "share" / "fonts" / "FiraCode"
    fonts_dir.mkdir(parents=True)
    (fonts_dir / "FiraCode-Retina.ttf").write_bytes(b"existing")

    with patch("machine_setup.windows.is_wsl", return_value=False):
        monkeypatch.setattr(installers.Path, "home", lambda: tmp_path)

        caplog.set_level("INFO", logger="machine_setup")
        installers.install_fira_code()

    assert "Fira Code already installed" in caplog.text


def test_install_fira_code_linux(tmp_path, monkeypatch, caplog) -> None:
    """Install Fira Code on native Linux: copies TTFs and runs fc-cache."""
    zip_data = _make_fira_code_zip()
    responses = [
        FakeResponse(_fira_code_api_payload(), status=200),
        FakeResponse(zip_data, status=200),
    ]

    monkeypatch.setattr(
        installers.urllib.request,
        "urlopen",
        lambda *args, **kwargs: responses.pop(0),
    )

    run_calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        run_calls.append(list(cmd))
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(installers, "run", fake_run)

    with patch("machine_setup.windows.is_wsl", return_value=False):
        monkeypatch.setattr(installers.Path, "home", lambda: tmp_path)

        caplog.set_level("INFO", logger="machine_setup")
        installers.install_fira_code()

    fonts_dir = tmp_path / ".local" / "share" / "fonts" / "FiraCode"
    assert (fonts_dir / "FiraCode-Retina.ttf").exists()
    assert any(cmd[0] == "fc-cache" for cmd in run_calls)
    assert "Fira Code installed" in caplog.text


def test_install_fira_code_wsl(tmp_path, monkeypatch, caplog) -> None:
    """Install Fira Code on WSL: copies TTFs and registers in Windows registry."""
    zip_data = _make_fira_code_zip()
    responses = [
        FakeResponse(_fira_code_api_payload(), status=200),
        FakeResponse(zip_data, status=200),
    ]

    monkeypatch.setattr(
        installers.urllib.request,
        "urlopen",
        lambda *args, **kwargs: responses.pop(0),
    )

    run_calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        run_calls.append(list(cmd))
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(installers, "run", fake_run)

    win_fonts = tmp_path / "WinFonts"

    with (
        patch("machine_setup.windows.is_wsl", return_value=True),
        patch("machine_setup.windows.get_windows_username", return_value="TestUser"),
        patch("machine_setup.windows.get_windows_fonts_dir", return_value=win_fonts),
    ):
        caplog.set_level("INFO", logger="machine_setup")
        installers.install_fira_code()

    assert (win_fonts / "FiraCode-Retina.ttf").exists()
    powershell_calls = [c for c in run_calls if c[0] == "powershell.exe"]
    assert len(powershell_calls) == len(installers.FIRA_CODE_FONT_NAMES)
    assert "Fira Code installed" in caplog.text


def test_install_fira_code_wsl_skip_windows(tmp_path, monkeypatch, caplog) -> None:
    """With skip_windows=True on WSL, install to Linux path instead."""
    zip_data = _make_fira_code_zip()
    responses = [
        FakeResponse(_fira_code_api_payload(), status=200),
        FakeResponse(zip_data, status=200),
    ]

    monkeypatch.setattr(
        installers.urllib.request,
        "urlopen",
        lambda *args, **kwargs: responses.pop(0),
    )

    def fake_run(cmd, **kwargs):
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(installers, "run", fake_run)

    with patch("machine_setup.windows.is_wsl", return_value=True):
        monkeypatch.setattr(installers.Path, "home", lambda: tmp_path)

        caplog.set_level("INFO", logger="machine_setup")
        installers.install_fira_code(skip_windows=True)

    fonts_dir = tmp_path / ".local" / "share" / "fonts" / "FiraCode"
    assert (fonts_dir / "FiraCode-Retina.ttf").exists()


def test_install_fira_code_no_zip_asset(monkeypatch) -> None:
    """Raise when no matching zip asset in release."""
    api_payload = json.dumps({"assets": []}).encode("utf-8")
    monkeypatch.setattr(
        installers.urllib.request,
        "urlopen",
        lambda *args, **kwargs: FakeResponse(api_payload, status=200),
    )

    with (
        patch("machine_setup.windows.is_wsl", return_value=False),
        pytest.raises(RuntimeError, match="Could not find Fira Code zip"),
    ):
        monkeypatch.setattr(installers.Path, "home", lambda: Path("/nonexistent"))
        installers.install_fira_code()


def test_install_fira_code_cleans_temp_on_failure(tmp_path, monkeypatch) -> None:
    """Remove temporary zip and extract directory when installation fails."""
    zip_data = _make_fira_code_zip()
    responses = [
        FakeResponse(_fira_code_api_payload(), status=200),
        FakeResponse(zip_data, status=200),
    ]

    monkeypatch.setattr(
        installers.urllib.request,
        "urlopen",
        lambda *args, **kwargs: responses.pop(0),
    )

    with patch("machine_setup.windows.is_wsl", return_value=False):
        monkeypatch.setattr(installers.Path, "home", lambda: tmp_path)

        # Force failure during copy phase
        monkeypatch.setattr(
            installers.shutil,
            "copy2",
            lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk full")),
        )

        removed_files: list[str] = []
        removed_dirs: list[str] = []
        real_remove = os.remove
        real_rmtree = shutil.rmtree

        def fake_remove(path: str) -> None:
            removed_files.append(path)
            real_remove(path)

        def fake_rmtree(path: str, **kwargs) -> None:
            removed_dirs.append(path)
            real_rmtree(path)

        monkeypatch.setattr(installers.os, "remove", fake_remove)
        monkeypatch.setattr(installers.shutil, "rmtree", fake_rmtree)

        with pytest.raises(OSError, match="disk full"):
            installers.install_fira_code()

    assert removed_files, "zip file cleanup was not attempted"
    assert not os.path.exists(removed_files[0])
    assert removed_dirs, "extract directory cleanup was not attempted"
    assert not os.path.exists(removed_dirs[0])


def test_install_fira_code_wsl_no_username(monkeypatch, caplog) -> None:
    """Skip when WSL but no Windows username detected."""
    with (
        patch("machine_setup.windows.is_wsl", return_value=True),
        patch("machine_setup.windows.get_windows_username", return_value=None),
    ):
        caplog.set_level(logging.WARNING, logger="machine_setup")
        installers.install_fira_code()

    assert "Could not detect Windows username" in caplog.text


def test_register_fira_code_windows_no_powershell(tmp_path, caplog) -> None:
    """Test graceful handling when powershell.exe is not available."""
    caplog.set_level(logging.WARNING)

    ttf_files = [tmp_path / "FiraCode-Regular.ttf"]
    ttf_files[0].write_bytes(b"fake")

    with patch("machine_setup.installers.run", side_effect=FileNotFoundError):
        installers._register_fira_code_windows(ttf_files)

    assert "powershell.exe not available" in caplog.text


def test_install_fira_code_api_network_error(monkeypatch, caplog) -> None:
    """Test error when GitHub API is unreachable."""
    import urllib.error

    with (
        patch("machine_setup.windows.is_wsl", return_value=False),
        patch(
            "machine_setup.installers.urllib.request.urlopen",
            side_effect=urllib.error.URLError("network error"),
        ),
    ):
        monkeypatch.setattr(installers.Path, "home", lambda: Path("/nonexistent"))

        with pytest.raises(RuntimeError, match="Failed to fetch Fira Code release metadata"):
            installers.install_fira_code()
