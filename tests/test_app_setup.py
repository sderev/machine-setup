"""Tests for app_setup module."""

import logging
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from machine_setup import app_setup
from machine_setup.app_setup import (
    get_current_shell,
    get_zsh_path,
    set_default_shell_zsh,
    setup_shell,
)

# --- IPython math profile tests ---


def test_setup_ipython_math_profile_skips_when_uv_missing(monkeypatch, caplog) -> None:
    """Skip setup when uv is not installed."""
    monkeypatch.setattr(app_setup, "command_exists", lambda _: False)

    caplog.set_level(logging.WARNING, logger="machine_setup")
    app_setup.setup_ipython_math_profile()

    assert "uv not found" in caplog.text


def test_setup_ipython_math_profile_creates_files(monkeypatch, tmp_path, caplog) -> None:
    """Create pyproject.toml, startup script, and wrapper script."""
    math_dir = tmp_path / "ipython-math"
    bin_dir = tmp_path / "bin"
    wrapper = bin_dir / "ipython-math"

    monkeypatch.setattr(app_setup, "command_exists", lambda _: True)
    monkeypatch.setattr(app_setup, "IPYTHON_MATH_DIR", math_dir)
    monkeypatch.setattr(app_setup, "IPYTHON_MATH_BIN", wrapper)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(returncode=0, stderr=""),
    )

    caplog.set_level(logging.INFO, logger="machine_setup")
    app_setup.setup_ipython_math_profile()

    assert (math_dir / "pyproject.toml").exists()
    assert wrapper.exists()
    assert wrapper.stat().st_mode & 0o755 == 0o755
    # Verify IPython profile config is created with vi mode
    config_file = math_dir / "profile_math" / "ipython_config.py"
    assert config_file.exists()
    config_content = config_file.read_text()
    assert 'editing_mode = "vi"' in config_content
    # Verify IPython profile startup script is created
    startup_script = math_dir / "profile_math" / "startup" / "00-imports.py"
    assert startup_script.exists()
    startup_content = startup_script.read_text()
    assert "import math" in startup_content
    assert "import numpy as np" in startup_content
    assert "import pandas as pd" in startup_content
    assert "IPython math profile setup complete" in caplog.text


def test_setup_ipython_math_profile_handles_sync_failure(monkeypatch, tmp_path, caplog) -> None:
    """Log warning and return early when uv sync fails."""
    math_dir = tmp_path / "ipython-math"
    bin_dir = tmp_path / "bin"
    wrapper = bin_dir / "ipython-math"

    monkeypatch.setattr(app_setup, "command_exists", lambda _: True)
    monkeypatch.setattr(app_setup, "IPYTHON_MATH_DIR", math_dir)
    monkeypatch.setattr(app_setup, "IPYTHON_MATH_BIN", wrapper)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(returncode=1, stderr="sync error"),
    )

    caplog.set_level(logging.WARNING, logger="machine_setup")
    app_setup.setup_ipython_math_profile()

    assert "Failed to sync" in caplog.text
    assert not wrapper.exists()


def test_setup_ipython_math_profile_preserves_existing_pyproject(
    monkeypatch, tmp_path, caplog
) -> None:
    """Do not overwrite existing pyproject.toml."""
    math_dir = tmp_path / "ipython-math"
    math_dir.mkdir(parents=True)
    pyproject = math_dir / "pyproject.toml"
    original_content = "# user modified content"
    pyproject.write_text(original_content)

    bin_dir = tmp_path / "bin"
    wrapper = bin_dir / "ipython-math"

    monkeypatch.setattr(app_setup, "command_exists", lambda _: True)
    monkeypatch.setattr(app_setup, "IPYTHON_MATH_DIR", math_dir)
    monkeypatch.setattr(app_setup, "IPYTHON_MATH_BIN", wrapper)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(returncode=0, stderr=""),
    )

    app_setup.setup_ipython_math_profile()

    assert pyproject.read_text() == original_content


# --- Shell tests ---


class TestGetCurrentShell:
    """Tests for get_current_shell function."""

    def test_normal_case(self):
        """Test that pwd.getpwuid returns shell path."""
        with patch("machine_setup.app_setup.pwd.getpwuid") as mock_getpwuid:
            mock_pw = Mock()
            mock_pw.pw_shell = "/bin/zsh"
            mock_getpwuid.return_value = mock_pw

            result = get_current_shell()
            assert result == "/bin/zsh"
            mock_getpwuid.assert_called_once()

    def test_keyerror_fallback_to_shell_env(self):
        """Test fallback to $SHELL when pwd.getpwuid raises KeyError."""
        with (
            patch("machine_setup.app_setup.pwd.getpwuid", side_effect=KeyError),
            patch.dict(os.environ, {"SHELL": "/usr/bin/zsh"}),
        ):
            result = get_current_shell()
            assert result == "/usr/bin/zsh"

    def test_keyerror_fallback_to_default(self):
        """Test fallback to /bin/bash when pwd.getpwuid raises KeyError and SHELL not set."""
        with (
            patch("machine_setup.app_setup.pwd.getpwuid", side_effect=KeyError),
            patch.dict(os.environ, {}, clear=True),
        ):
            result = get_current_shell()
            assert result == "/bin/bash"


class TestGetZshPath:
    """Tests for get_zsh_path function."""

    def test_zsh_found(self):
        """Test that zsh path is returned when found."""
        with patch("machine_setup.app_setup.run") as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = "/usr/bin/zsh\n"
            mock_run.return_value = mock_result

            result = get_zsh_path()
            assert result == "/usr/bin/zsh"
            mock_run.assert_called_once_with(["which", "zsh"], check=False, capture=True)

    def test_zsh_not_found(self):
        """Test that None is returned when zsh is not found."""
        with patch("machine_setup.app_setup.run") as mock_run:
            mock_result = Mock()
            mock_result.returncode = 1
            mock_run.return_value = mock_result

            result = get_zsh_path()
            assert result is None


class TestSetDefaultShellZsh:
    """Tests for set_default_shell_zsh function."""

    @patch("machine_setup.app_setup.logger")
    def test_early_return_zsh_already_default(self, mock_logger):
        """Test early return when zsh is already the default shell."""
        with patch("machine_setup.app_setup.get_current_shell", return_value="/bin/zsh"):
            set_default_shell_zsh()
            mock_logger.info.assert_called_once_with("zsh is already the default shell")

    @patch("machine_setup.app_setup.logger")
    def test_early_return_zsh_not_found(self, mock_logger):
        """Test early return when zsh is not found in PATH."""
        with (
            patch("machine_setup.app_setup.get_current_shell", return_value="/bin/bash"),
            patch("machine_setup.app_setup.get_zsh_path", return_value=None),
        ):
            set_default_shell_zsh()
            mock_logger.error.assert_called_once_with("zsh not found in PATH")

    @patch("machine_setup.app_setup.logger")
    def test_adds_zsh_to_shells_when_missing(self, mock_logger):
        """Test that zsh is added to /etc/shells when missing."""
        zsh_path = "/usr/bin/zsh"

        with (
            patch("machine_setup.app_setup.get_current_shell", return_value="/bin/bash"),
            patch("machine_setup.app_setup.get_zsh_path", return_value=zsh_path),
            patch("machine_setup.app_setup.sudo_prefix", return_value=["sudo"]),
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "read_text", return_value="/bin/bash\n/bin/sh\n"),
            patch("machine_setup.app_setup.run") as mock_run,
        ):
            set_default_shell_zsh()

            mock_logger.info.assert_any_call("Adding %s to /etc/shells", zsh_path)
            mock_run.assert_any_call(
                ["sudo", "sh", "-c", 'printf "%s\\n" "$1" >> /etc/shells', "_", zsh_path]
            )

    @patch("machine_setup.app_setup.logger")
    def test_etc_shells_not_found(self, mock_logger):
        """Test early return when /etc/shells does not exist."""
        zsh_path = "/usr/bin/zsh"

        with (
            patch("machine_setup.app_setup.get_current_shell", return_value="/bin/bash"),
            patch("machine_setup.app_setup.get_zsh_path", return_value=zsh_path),
            patch("machine_setup.app_setup.sudo_prefix", return_value=["sudo"]),
            patch.object(Path, "exists", return_value=False),
            patch("machine_setup.app_setup.run") as mock_run,
            patch("machine_setup.app_setup.pwd.getpwuid") as mock_getpwuid,
        ):
            mock_pw = Mock()
            mock_pw.pw_name = "testuser"
            mock_getpwuid.return_value = mock_pw

            set_default_shell_zsh()

            chsh_args = [call[0][0] for call in mock_run.call_args_list]
            assert ["sudo", "chsh", "-s", zsh_path, "testuser"] in chsh_args

    @patch("machine_setup.app_setup.logger")
    def test_does_not_add_zsh_to_shells_when_present(self, mock_logger):
        """Test that zsh is not added to /etc/shells when already present."""
        zsh_path = "/usr/bin/zsh"

        with (
            patch("machine_setup.app_setup.get_current_shell", return_value="/bin/bash"),
            patch("machine_setup.app_setup.get_zsh_path", return_value=zsh_path),
            patch("machine_setup.app_setup.sudo_prefix", return_value=["sudo"]),
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "read_text", return_value="/bin/bash\n/usr/bin/zsh\n"),
            patch("machine_setup.app_setup.run") as mock_run,
            patch("machine_setup.app_setup.pwd.getpwuid") as mock_getpwuid,
        ):
            mock_pw = Mock()
            mock_pw.pw_name = "testuser"
            mock_getpwuid.return_value = mock_pw

            set_default_shell_zsh()

            calls = [call[0][0] for call in mock_run.call_args_list]
            assert f"echo '{zsh_path}' >> /etc/shells" not in str(calls)
            assert ["sudo", "chsh", "-s", zsh_path, "testuser"] in calls

    @patch("machine_setup.app_setup.logger")
    def test_sets_default_shell(self, mock_logger):
        """Test that default shell is changed to zsh."""
        zsh_path = "/usr/bin/zsh"

        with (
            patch("machine_setup.app_setup.get_current_shell", return_value="/bin/bash"),
            patch("machine_setup.app_setup.get_zsh_path", return_value=zsh_path),
            patch("machine_setup.app_setup.sudo_prefix", return_value=["sudo"]),
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "read_text", return_value="/bin/bash\n"),
            patch("machine_setup.app_setup.run") as mock_run,
            patch("machine_setup.app_setup.pwd.getpwuid") as mock_getpwuid,
        ):
            mock_pw = Mock()
            mock_pw.pw_name = "testuser"
            mock_getpwuid.return_value = mock_pw

            set_default_shell_zsh()

            chsh_args = [call[0][0] for call in mock_run.call_args_list]
            assert ["sudo", "chsh", "-s", zsh_path, "testuser"] in chsh_args
            mock_logger.info.assert_any_call("Setting default shell to zsh...")
            mock_logger.info.assert_any_call(
                "Default shell changed to zsh (effective on next login)"
            )


class TestSetupShell:
    """Tests for setup_shell function."""

    @patch("machine_setup.app_setup.logger")
    def test_sets_shell_when_zsh_installed(self, mock_logger):
        """Test that set_default_shell_zsh is called when zsh is installed."""
        with (
            patch("machine_setup.app_setup.command_exists", return_value=True),
            patch("machine_setup.app_setup.set_default_shell_zsh") as mock_set_shell,
        ):
            setup_shell()
            mock_set_shell.assert_called_once()

    @patch("machine_setup.app_setup.logger")
    def test_warnings_when_zsh_not_installed(self, mock_logger):
        """Test warning is logged when zsh is not installed."""
        with (
            patch("machine_setup.app_setup.command_exists", return_value=False),
            patch("machine_setup.app_setup.set_default_shell_zsh") as mock_set_shell,
        ):
            setup_shell()
            mock_set_shell.assert_not_called()
            mock_logger.warning.assert_called_once_with(
                "zsh not installed, cannot set as default shell"
            )
