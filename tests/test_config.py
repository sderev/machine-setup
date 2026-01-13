"""Tests for config module."""

import pytest

from machine_setup.config import (
    NPM_TOOLS_DEV,
    NPM_TOOLS_FULL,
    NPM_TOOLS_MINIMAL,
    PACKAGES_DEV,
    PACKAGES_FULL,
    PACKAGES_MINIMAL,
    STOW_PACKAGES,
    Preset,
    SetupConfig,
)


class TestPreset:
    """Tests for Preset enum."""

    def test_preset_values(self):
        """Test preset enum values."""
        assert Preset.MINIMAL.value == "minimal"
        assert Preset.DEV.value == "dev"
        assert Preset.FULL.value == "full"

    def test_preset_from_string(self):
        """Test creating preset from string."""
        assert Preset("minimal") == Preset.MINIMAL
        assert Preset("dev") == Preset.DEV
        assert Preset("full") == Preset.FULL

    def test_preset_invalid_string(self):
        """Test that invalid string raises ValueError."""
        with pytest.raises(ValueError):
            Preset("invalid")


class TestSetupConfig:
    """Tests for SetupConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = SetupConfig(preset=Preset.DEV)
        assert config.preset == Preset.DEV
        assert "github.com" in config.dotfiles_repo
        assert config.dotfiles_dir == "~/.dotfiles_private"
        assert config.home_dir == "~"

    def test_custom_dotfiles_repo(self):
        """Test custom dotfiles repo."""
        config = SetupConfig(
            preset=Preset.MINIMAL,
            dotfiles_repo="https://github.com/user/dotfiles.git",
        )
        assert config.dotfiles_repo == "https://github.com/user/dotfiles.git"

    def test_config_is_frozen(self):
        """Test that config is immutable."""
        config = SetupConfig(preset=Preset.DEV)
        with pytest.raises(AttributeError):
            config.preset = Preset.FULL  # type: ignore[misc]


class TestGetPackages:
    """Tests for SetupConfig.get_packages method."""

    def test_minimal_packages(self):
        """Test minimal preset returns only minimal packages."""
        config = SetupConfig(preset=Preset.MINIMAL)
        packages = config.get_packages()
        assert set(packages) == set(PACKAGES_MINIMAL)

    def test_dev_packages(self):
        """Test dev preset returns minimal + dev packages."""
        config = SetupConfig(preset=Preset.DEV)
        packages = config.get_packages()
        expected = set(PACKAGES_MINIMAL) | set(PACKAGES_DEV)
        assert set(packages) == expected

    def test_full_packages(self):
        """Test full preset returns all packages."""
        config = SetupConfig(preset=Preset.FULL)
        packages = config.get_packages()
        expected = set(PACKAGES_MINIMAL) | set(PACKAGES_DEV) | set(PACKAGES_FULL)
        assert set(packages) == expected

    def test_packages_include_git(self):
        """Test that git is always included."""
        for preset in Preset:
            config = SetupConfig(preset=preset)
            assert "git" in config.get_packages()


class TestGetStowPackages:
    """Tests for SetupConfig.get_stow_packages method."""

    def test_minimal_stow_packages(self):
        """Test minimal preset stow packages."""
        config = SetupConfig(preset=Preset.MINIMAL)
        assert config.get_stow_packages() == STOW_PACKAGES[Preset.MINIMAL]

    def test_dev_stow_packages(self):
        """Test dev preset stow packages."""
        config = SetupConfig(preset=Preset.DEV)
        assert config.get_stow_packages() == STOW_PACKAGES[Preset.DEV]

    def test_full_stow_packages(self):
        """Test full preset stow packages."""
        config = SetupConfig(preset=Preset.FULL)
        assert config.get_stow_packages() == STOW_PACKAGES[Preset.FULL]

    def test_stow_always_includes_shell_and_git(self):
        """Test that shell and git are always stowed."""
        for preset in Preset:
            config = SetupConfig(preset=preset)
            stow_pkgs = config.get_stow_packages()
            assert "shell" in stow_pkgs
            assert "git" in stow_pkgs


class TestGetNpmTools:
    """Tests for SetupConfig.get_npm_tools method."""

    def test_minimal_npm_tools(self):
        """Test minimal preset returns minimal npm tools."""
        config = SetupConfig(preset=Preset.MINIMAL)
        tools = config.get_npm_tools()
        assert set(tools) == set(NPM_TOOLS_MINIMAL)

    def test_dev_npm_tools(self):
        """Test dev preset returns minimal + dev npm tools."""
        config = SetupConfig(preset=Preset.DEV)
        tools = config.get_npm_tools()
        expected = set(NPM_TOOLS_MINIMAL) | set(NPM_TOOLS_DEV)
        assert set(tools) == expected

    def test_full_npm_tools(self):
        """Test full preset returns all npm tools."""
        config = SetupConfig(preset=Preset.FULL)
        tools = config.get_npm_tools()
        expected = set(NPM_TOOLS_MINIMAL) | set(NPM_TOOLS_DEV) | set(NPM_TOOLS_FULL)
        assert set(tools) == expected
