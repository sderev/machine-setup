"""Tests for ipython_setup module."""

import logging
import subprocess
from types import SimpleNamespace

from machine_setup import ipython_setup


def test_setup_ipython_math_profile_skips_when_uv_missing(monkeypatch, caplog) -> None:
    """Skip setup when uv is not installed."""
    monkeypatch.setattr(ipython_setup, "command_exists", lambda _: False)

    caplog.set_level(logging.WARNING, logger="machine_setup")
    ipython_setup.setup_ipython_math_profile()

    assert "uv not found" in caplog.text


def test_setup_ipython_math_profile_creates_files(monkeypatch, tmp_path, caplog) -> None:
    """Create pyproject.toml and wrapper script."""
    math_dir = tmp_path / "ipython-math"
    bin_dir = tmp_path / "bin"
    wrapper = bin_dir / "ipython-math"

    monkeypatch.setattr(ipython_setup, "command_exists", lambda _: True)
    monkeypatch.setattr(ipython_setup, "IPYTHON_MATH_DIR", math_dir)
    monkeypatch.setattr(ipython_setup, "IPYTHON_MATH_BIN", wrapper)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(returncode=0, stderr=""),
    )

    caplog.set_level(logging.INFO, logger="machine_setup")
    ipython_setup.setup_ipython_math_profile()

    assert (math_dir / "pyproject.toml").exists()
    assert wrapper.exists()
    assert wrapper.stat().st_mode & 0o755 == 0o755
    assert "IPython math profile setup complete" in caplog.text


def test_setup_ipython_math_profile_handles_sync_failure(monkeypatch, tmp_path, caplog) -> None:
    """Log warning and return early when uv sync fails."""
    math_dir = tmp_path / "ipython-math"
    bin_dir = tmp_path / "bin"
    wrapper = bin_dir / "ipython-math"

    monkeypatch.setattr(ipython_setup, "command_exists", lambda _: True)
    monkeypatch.setattr(ipython_setup, "IPYTHON_MATH_DIR", math_dir)
    monkeypatch.setattr(ipython_setup, "IPYTHON_MATH_BIN", wrapper)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(returncode=1, stderr="sync error"),
    )

    caplog.set_level(logging.WARNING, logger="machine_setup")
    ipython_setup.setup_ipython_math_profile()

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

    monkeypatch.setattr(ipython_setup, "command_exists", lambda _: True)
    monkeypatch.setattr(ipython_setup, "IPYTHON_MATH_DIR", math_dir)
    monkeypatch.setattr(ipython_setup, "IPYTHON_MATH_BIN", wrapper)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(returncode=0, stderr=""),
    )

    ipython_setup.setup_ipython_math_profile()

    assert pyproject.read_text() == original_content
