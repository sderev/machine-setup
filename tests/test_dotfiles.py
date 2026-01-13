"""Tests for dotfiles module."""

import logging
from pathlib import Path

from pytest import LogCaptureFixture

from machine_setup.dotfiles import remove_default_dotfiles, setup_scripts_symlink


def test_remove_default_dotfiles_backs_up_files(tmp_path: Path) -> None:
    """Existing default dotfiles are moved aside."""
    dotfiles = [".bashrc", ".profile", ".bash_logout", ".gitconfig"]
    for dotfile in dotfiles:
        (tmp_path / dotfile).write_text("data")

    remove_default_dotfiles(tmp_path)

    for dotfile in dotfiles:
        original = tmp_path / dotfile
        assert not original.exists()
        backups = list(tmp_path.glob(f"{dotfile}.bak.*"))
        assert backups


def test_remove_default_dotfiles_keeps_symlinks(tmp_path: Path) -> None:
    """Symlinked dotfiles are left in place."""
    target = tmp_path / ".bashrc"
    real_file = tmp_path / "bashrc"
    real_file.write_text("data")
    target.symlink_to(real_file)

    remove_default_dotfiles(tmp_path)

    assert target.is_symlink()
    backups = list(tmp_path.glob(".bashrc.bak.*"))
    assert not backups


def test_setup_scripts_symlink_creates_symlink(
    tmp_path: Path,
    caplog: LogCaptureFixture,
) -> None:
    """Scripts directory becomes ~/.scripts symlink."""
    dotfiles_path = tmp_path / "dotfiles"
    home = tmp_path / "home"
    scripts_src = dotfiles_path / "scripts"
    scripts_src.mkdir(parents=True)
    home.mkdir()

    caplog.set_level(logging.INFO, logger="machine_setup")
    setup_scripts_symlink(dotfiles_path, home)

    scripts_dst = home / ".scripts"
    assert scripts_dst.is_symlink()
    assert scripts_dst.resolve() == scripts_src.resolve()
    assert "Created symlink" in caplog.text


def test_setup_scripts_symlink_warns_when_destination_exists(
    tmp_path: Path,
    caplog: LogCaptureFixture,
) -> None:
    """Existing non-symlink ~/.scripts is left alone."""
    dotfiles_path = tmp_path / "dotfiles"
    home = tmp_path / "home"
    scripts_src = dotfiles_path / "scripts"
    scripts_src.mkdir(parents=True)
    home.mkdir()

    scripts_dst = home / ".scripts"
    scripts_dst.write_text("not a symlink")

    caplog.set_level(logging.WARNING, logger="machine_setup")
    setup_scripts_symlink(dotfiles_path, home)

    assert scripts_dst.is_file()
    assert "exists and is not a symlink" in caplog.text
