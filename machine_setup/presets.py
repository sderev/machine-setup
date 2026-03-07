"""Preset definitions and package tiers."""

from dataclasses import dataclass
from enum import Enum

from machine_setup.private_config import PresetSettings, PrivateConfig


class Preset(str, Enum):
    MINIMAL = "minimal"  # Containers: essential CLI only
    DEV = "dev"  # VMs: development tools, no GUI
    FULL = "full"  # Workstations: everything + GUI


@dataclass(frozen=True)
class SetupConfig:
    """Configuration for the setup process."""

    preset: Preset
    dotfiles_repo: str
    dotfiles_dir: str
    dotfiles_branch: str
    repos_owner_namespace: str
    preset_settings: dict[Preset, PresetSettings]
    home_dir: str = "~"

    @classmethod
    def from_private_config(
        cls,
        *,
        preset: Preset,
        private_config: PrivateConfig,
        dotfiles_repo: str,
        dotfiles_dir: str,
        dotfiles_branch: str,
        home_dir: str = "~",
    ) -> "SetupConfig":
        """Build runtime setup config from loaded private config."""
        settings = {
            Preset.MINIMAL: private_config.presets[Preset.MINIMAL.value],
            Preset.DEV: private_config.presets[Preset.DEV.value],
            Preset.FULL: private_config.presets[Preset.FULL.value],
        }
        return cls(
            preset=preset,
            dotfiles_repo=dotfiles_repo,
            dotfiles_dir=dotfiles_dir,
            dotfiles_branch=dotfiles_branch,
            repos_owner_namespace=private_config.repos.owner_namespace,
            preset_settings=settings,
            home_dir=home_dir,
        )

    def get_packages(self) -> list[str]:
        """Return packages for current preset (cumulative)."""
        packages = list(self.preset_settings[Preset.MINIMAL].packages)
        if self.preset in (Preset.DEV, Preset.FULL):
            packages.extend(self.preset_settings[Preset.DEV].packages)
        if self.preset == Preset.FULL:
            packages.extend(self.preset_settings[Preset.FULL].packages)
        return packages

    def get_stow_packages(self) -> list[str]:
        """Return stow packages for current preset."""
        return list(self.preset_settings[self.preset].stow_packages)

    def get_uv_tools(self) -> list[str]:
        """Return uv tools for current preset (cumulative)."""
        tools = list(self.preset_settings[Preset.MINIMAL].uv_tools)
        if self.preset in (Preset.DEV, Preset.FULL):
            tools.extend(self.preset_settings[Preset.DEV].uv_tools)
        if self.preset == Preset.FULL:
            tools.extend(self.preset_settings[Preset.FULL].uv_tools)
        return tools

    def get_npm_tools(self) -> list[str]:
        """Return npm tools for current preset (cumulative)."""
        tools = list(self.preset_settings[Preset.MINIMAL].npm_tools)
        if self.preset in (Preset.DEV, Preset.FULL):
            tools.extend(self.preset_settings[Preset.DEV].npm_tools)
        if self.preset == Preset.FULL:
            tools.extend(self.preset_settings[Preset.FULL].npm_tools)
        return tools
