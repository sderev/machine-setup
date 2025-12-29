"""Tests for dotfiles module."""

from pathlib import Path

from machine_setup.dotfiles import remove_default_dotfiles


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
