"""Tests for utils module."""

from pathlib import Path
from unittest.mock import patch

from machine_setup.utils import command_exists, ensure_dir, path_exists


class TestCommandExists:
    """Tests for command_exists function."""

    def test_existing_command(self):
        """Test that existing commands are found."""
        assert command_exists("sh") is True
        assert command_exists("python3") is True

    def test_nonexistent_command(self):
        """Test that nonexistent commands return False."""
        assert command_exists("nonexistent_command_12345") is False

    def test_empty_string(self):
        """Test that empty string returns False."""
        assert command_exists("") is False


class TestPathExists:
    """Tests for path_exists function."""

    def test_existing_path(self, tmp_path: Path):
        """Test that existing paths return True."""
        test_file = tmp_path / "test.txt"
        test_file.touch()
        assert path_exists(str(test_file)) is True

    def test_nonexistent_path(self, tmp_path: Path):
        """Test that nonexistent paths return False."""
        assert path_exists(str(tmp_path / "nonexistent")) is False

    def test_tilde_expansion(self):
        """Test that ~ is expanded."""
        assert path_exists("~") is True

    def test_path_object(self, tmp_path: Path):
        """Test that Path objects work."""
        test_file = tmp_path / "test.txt"
        test_file.touch()
        assert path_exists(test_file) is True


class TestEnsureDir:
    """Tests for ensure_dir function."""

    def test_creates_directory(self, tmp_path: Path):
        """Test that directory is created."""
        new_dir = tmp_path / "new" / "nested" / "dir"
        result = ensure_dir(new_dir)
        assert new_dir.exists()
        assert new_dir.is_dir()
        assert result == new_dir

    def test_existing_directory(self, tmp_path: Path):
        """Test that existing directory is returned."""
        result = ensure_dir(tmp_path)
        assert result == tmp_path

    def test_returns_path_object(self, tmp_path: Path):
        """Test that Path object is returned."""
        result = ensure_dir(str(tmp_path / "new"))
        assert isinstance(result, Path)

    def test_tilde_expansion(self, tmp_path: Path):
        """Test that ~ is expanded."""
        with patch.object(Path, "expanduser", return_value=tmp_path / "home"):
            result = ensure_dir("~/test")
            assert isinstance(result, Path)
