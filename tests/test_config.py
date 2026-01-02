"""Tests for config module."""

import pytest

from machine_setup.config import (
    PACKAGES_DEV,
    PACKAGES_FULL,
    PACKAGES_MINIMAL,
    STOW_PACKAGES,
    Profile,
    SetupConfig,
)


class TestProfile:
    """Tests for Profile enum."""

    def test_profile_values(self):
        """Test profile enum values."""
        assert Profile.MINIMAL.value == "minimal"
        assert Profile.DEV.value == "dev"
        assert Profile.FULL.value == "full"

    def test_profile_from_string(self):
        """Test creating profile from string."""
        assert Profile("minimal") == Profile.MINIMAL
        assert Profile("dev") == Profile.DEV
        assert Profile("full") == Profile.FULL

    def test_profile_invalid_string(self):
        """Test that invalid string raises ValueError."""
        with pytest.raises(ValueError):
            Profile("invalid")


class TestSetupConfig:
    """Tests for SetupConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = SetupConfig(profile=Profile.DEV)
        assert config.profile == Profile.DEV
        assert "github.com" in config.dotfiles_repo
        assert config.dotfiles_dir == "~/.dotfiles_private"
        assert config.home_dir == "~"

    def test_custom_dotfiles_repo(self):
        """Test custom dotfiles repo."""
        config = SetupConfig(
            profile=Profile.MINIMAL,
            dotfiles_repo="https://github.com/user/dotfiles.git",
        )
        assert config.dotfiles_repo == "https://github.com/user/dotfiles.git"

    def test_config_is_frozen(self):
        """Test that config is immutable."""
        config = SetupConfig(profile=Profile.DEV)
        with pytest.raises(AttributeError):
            config.profile = Profile.FULL  # type: ignore[misc]


class TestGetPackages:
    """Tests for SetupConfig.get_packages method."""

    def test_minimal_packages(self):
        """Test minimal profile returns only minimal packages."""
        config = SetupConfig(profile=Profile.MINIMAL)
        packages = config.get_packages()
        assert set(packages) == set(PACKAGES_MINIMAL)

    def test_dev_packages(self):
        """Test dev profile returns minimal + dev packages."""
        config = SetupConfig(profile=Profile.DEV)
        packages = config.get_packages()
        expected = set(PACKAGES_MINIMAL) | set(PACKAGES_DEV)
        assert set(packages) == expected

    def test_full_packages(self):
        """Test full profile returns all packages."""
        config = SetupConfig(profile=Profile.FULL)
        packages = config.get_packages()
        expected = set(PACKAGES_MINIMAL) | set(PACKAGES_DEV) | set(PACKAGES_FULL)
        assert set(packages) == expected

    def test_packages_include_git(self):
        """Test that git is always included."""
        for profile in Profile:
            config = SetupConfig(profile=profile)
            assert "git" in config.get_packages()


class TestGetStowPackages:
    """Tests for SetupConfig.get_stow_packages method."""

    def test_minimal_stow_packages(self):
        """Test minimal profile stow packages."""
        config = SetupConfig(profile=Profile.MINIMAL)
        assert config.get_stow_packages() == STOW_PACKAGES[Profile.MINIMAL]

    def test_dev_stow_packages(self):
        """Test dev profile stow packages."""
        config = SetupConfig(profile=Profile.DEV)
        assert config.get_stow_packages() == STOW_PACKAGES[Profile.DEV]

    def test_full_stow_packages(self):
        """Test full profile stow packages."""
        config = SetupConfig(profile=Profile.FULL)
        assert config.get_stow_packages() == STOW_PACKAGES[Profile.FULL]

    def test_stow_always_includes_shell_and_git(self):
        """Test that shell and git are always stowed."""
        for profile in Profile:
            config = SetupConfig(profile=profile)
            stow_pkgs = config.get_stow_packages()
            assert "shell" in stow_pkgs
            assert "git" in stow_pkgs
