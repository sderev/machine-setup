"""Preset definitions and package tiers."""

from dataclasses import dataclass
from enum import Enum
from typing import Final


class Preset(str, Enum):
    MINIMAL = "minimal"  # Containers: essential CLI only
    DEV = "dev"  # VMs: development tools, no GUI
    FULL = "full"  # Workstations: everything + GUI


PACKAGES_MINIMAL: Final[list[str]] = [
    "git",
    "vim",
    "zsh",
    "tmux",
    "curl",
    "wget",
    "ripgrep",
    "fzf",
    "bat",
    "btop",
    "gh",
    "jq",
    "tree",
    "stow",
    "ca-certificates",
]

PACKAGES_DEV: Final[list[str]] = [
    "gcc",
    "g++",
    "make",
    "golang",
    "python3",
    "python-is-python3",
    "python3-venv",
    "python3-pip",
    "podman",
    "git-delta",
    "shellcheck",
    "shfmt",
    "entr",
    "parallel",
    "gdb",
    "ssh",
]

PACKAGES_FULL: Final[list[str]] = [
    "texlive",
    "tex-common",
    "latexmk",
    "pandoc",
    "zathura",
    "xclip",
    "clang",
    "clang-format",
]

UV_TOOLS_MINIMAL: Final[list[str]] = []

UV_TOOLS_DEV: Final[list[str]] = [
    "ruff",
    "ty",
    "lmterminal",
    "lmtoolbox",
    "wslshot",
    "toc-markdown",
    "ast-grep-cli",
    "files-to-prompt",
    "llm",
    "vocabmaster",
]

UV_TOOLS_FULL: Final[list[str]] = []

STOW_PACKAGES: Final[dict[Preset, list[str]]] = {
    Preset.MINIMAL: ["shell", "git"],
    Preset.DEV: ["shell", "git", "vim", "tmux", "scripts", "config", "ai-tools"],
    Preset.FULL: [
        "shell",
        "git",
        "vim",
        "tmux",
        "scripts",
        "config",
        "ai-tools",
        "gui",
    ],
}


@dataclass(frozen=True)
class SetupConfig:
    """Configuration for the setup process."""

    preset: Preset
    dotfiles_repo: str = "https://github.com/sderev/.dotfiles_private.git"
    dotfiles_dir: str = "~/.dotfiles_private"
    dotfiles_branch: str = "main"
    home_dir: str = "~"

    def get_packages(self) -> list[str]:
        """Return packages for current preset (cumulative)."""
        packages = list(PACKAGES_MINIMAL)
        if self.preset in (Preset.DEV, Preset.FULL):
            packages.extend(PACKAGES_DEV)
        if self.preset == Preset.FULL:
            packages.extend(PACKAGES_FULL)
        return packages

    def get_stow_packages(self) -> list[str]:
        """Return stow packages for current preset."""
        return STOW_PACKAGES[self.preset]

    def get_uv_tools(self) -> list[str]:
        """Return uv tools for current preset (cumulative)."""
        tools = list(UV_TOOLS_MINIMAL)
        if self.preset in (Preset.DEV, Preset.FULL):
            tools.extend(UV_TOOLS_DEV)
        if self.preset == Preset.FULL:
            tools.extend(UV_TOOLS_FULL)
        return tools
