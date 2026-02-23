"""Tests for presets module."""

import pytest

from machine_setup.presets import Preset, SetupConfig
from machine_setup.private_config import (
    PresetSettings,
    PrivateConfig,
    ReposSettings,
    SetupSettings,
    WslSettings,
)


def _private_config() -> PrivateConfig:
    return PrivateConfig(
        setup=SetupSettings(timezone="America/New_York"),
        repos=ReposSettings(owner_namespace="acme"),
        presets={
            "minimal": PresetSettings(
                packages=["git", "curl"],
                uv_tools=["ruff"],
                npm_tools=["@ccusage/codex"],
                stow_packages=["shell", "git"],
            ),
            "dev": PresetSettings(
                packages=["gcc"],
                uv_tools=["ty"],
                npm_tools=["opencode-ai"],
                stow_packages=["shell", "git", "vim"],
            ),
            "full": PresetSettings(
                packages=["texlive"],
                uv_tools=["wslshot"],
                npm_tools=["@openai/codex"],
                stow_packages=["shell", "git", "vim", "gui"],
            ),
        },
        wsl=WslSettings(apply_wslconfig=True),
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

    def test_from_private_config(self):
        """Runtime config is built from private config values."""
        config = SetupConfig.from_private_config(
            preset=Preset.DEV,
            private_config=_private_config(),
            dotfiles_repo="https://github.com/acme/.dotfiles_private.git",
            dotfiles_dir="/home/user/Repos/github.com/acme/.dotfiles_private",
            dotfiles_branch="main",
        )
        assert config.preset == Preset.DEV
        assert config.dotfiles_repo == "https://github.com/acme/.dotfiles_private.git"
        assert config.dotfiles_branch == "main"
        assert config.repos_owner_namespace == "acme"

    def test_config_is_frozen(self):
        """Test that config is immutable."""
        config = SetupConfig.from_private_config(
            preset=Preset.DEV,
            private_config=_private_config(),
            dotfiles_repo="https://github.com/acme/.dotfiles_private.git",
            dotfiles_dir="/tmp/.dotfiles_private",
            dotfiles_branch="main",
        )
        with pytest.raises(AttributeError):
            config.preset = Preset.FULL  # type: ignore[misc]


class TestGetPackages:
    """Tests for SetupConfig.get_packages method."""

    def test_minimal_packages(self):
        """Test minimal preset returns only minimal packages."""
        config = SetupConfig.from_private_config(
            preset=Preset.MINIMAL,
            private_config=_private_config(),
            dotfiles_repo="https://github.com/acme/.dotfiles_private.git",
            dotfiles_dir="/tmp/.dotfiles_private",
            dotfiles_branch="main",
        )
        assert config.get_packages() == ["git", "curl"]

    def test_dev_packages(self):
        """Test dev preset returns minimal + dev packages."""
        config = SetupConfig.from_private_config(
            preset=Preset.DEV,
            private_config=_private_config(),
            dotfiles_repo="https://github.com/acme/.dotfiles_private.git",
            dotfiles_dir="/tmp/.dotfiles_private",
            dotfiles_branch="main",
        )
        assert config.get_packages() == ["git", "curl", "gcc"]

    def test_full_packages(self):
        """Test full preset returns all packages."""
        config = SetupConfig.from_private_config(
            preset=Preset.FULL,
            private_config=_private_config(),
            dotfiles_repo="https://github.com/acme/.dotfiles_private.git",
            dotfiles_dir="/tmp/.dotfiles_private",
            dotfiles_branch="main",
        )
        assert config.get_packages() == ["git", "curl", "gcc", "texlive"]


class TestGetStowPackages:
    """Tests for SetupConfig.get_stow_packages method."""

    def test_stow_uses_current_preset_only(self):
        """Stow packages are not cumulative."""
        config = SetupConfig.from_private_config(
            preset=Preset.FULL,
            private_config=_private_config(),
            dotfiles_repo="https://github.com/acme/.dotfiles_private.git",
            dotfiles_dir="/tmp/.dotfiles_private",
            dotfiles_branch="main",
        )
        assert config.get_stow_packages() == ["shell", "git", "vim", "gui"]


class TestToolLists:
    """Tests for uv/npm tool list composition."""

    def test_uv_tools_are_cumulative(self):
        """UV tools should be composed from lower presets."""
        config = SetupConfig.from_private_config(
            preset=Preset.FULL,
            private_config=_private_config(),
            dotfiles_repo="https://github.com/acme/.dotfiles_private.git",
            dotfiles_dir="/tmp/.dotfiles_private",
            dotfiles_branch="main",
        )
        assert config.get_uv_tools() == ["ruff", "ty", "wslshot"]

    def test_npm_tools_are_cumulative(self):
        """NPM tools should be composed from lower presets."""
        config = SetupConfig.from_private_config(
            preset=Preset.FULL,
            private_config=_private_config(),
            dotfiles_repo="https://github.com/acme/.dotfiles_private.git",
            dotfiles_dir="/tmp/.dotfiles_private",
            dotfiles_branch="main",
        )
        assert config.get_npm_tools() == ["@ccusage/codex", "opencode-ai", "@openai/codex"]
