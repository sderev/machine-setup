"""Preset definitions and package tiers."""

from dataclasses import dataclass
from enum import Enum


class Preset(str, Enum):
    MINIMAL = "minimal"  # Containers: essential CLI only
    DEV = "dev"  # VMs: development tools, no GUI
    FULL = "full"  # Workstations: everything + GUI


PACKAGES_MINIMAL: list[str] = [
    "bat",
    "btop",
    "ca-certificates",
    "coreutils",
    "curl",
    "fzf",
    "gh",
    "git",
    "jq",
    "locales",
    "man",
    "ripgrep",
    "stow",
    "sudo",
    "tmux",
    "vim",
    "wget",
    "zsh",
]

PACKAGES_DEV: list[str] = [
    "at",
    "ccache",
    "clang",
    "clang-format",
    "cloc",
    "cmake",
    "cron",
    "dnsutils",
    "entr",
    "g++",
    "gcc",
    "gdb",
    "git-delta",
    "golang",
    "hyperfine",
    "lua5.4",
    "luarocks",
    "make",
    "net-tools",
    "nodejs",
    "npm",
    "openssl",
    "parallel",
    "podman",
    "python-is-python3",
    "python3",
    "ipython3",
    "rlwrap",
    "rsync",
    "rustc",
    "shellcheck",
    "shfmt",
    "socat",
    "sqlite3",
    "ssh",
    "stress",
    "traceroute",
    "w3m",
    "whois",
]

PACKAGES_FULL: list[str] = [
    "ffmpeg",
    "imagemagick",
    "img2pdf",
    "latexmk",
    "libimage-exiftool-perl",
    # "love",  # Disabled: Debian sid package has broken postinst (missing man page)
    "msmtp",
    "msmtp-mta",
    "ncal",
    "optipng",
    "pandoc",
    "poppler-utils",
    "qpdf",
    "rename",
    "tex-common",
    "texlive",
    "tree",
    "xclip",
    "zathura",
]

UV_TOOLS_MINIMAL: list[str] = []

UV_TOOLS_DEV: list[str] = [
    "ast-grep-cli",
    "files-to-prompt",
    "llm",
    "lmterminal",
    "lmtoolbox",
    "ruff",
    "toc-markdown",
    "ty",
    "vocabmaster",
    "wslshot",
]

UV_TOOLS_FULL: list[str] = []

NPM_TOOLS_MINIMAL: list[str] = []

NPM_TOOLS_DEV: list[str] = [
    "@ccusage/codex",
    "@openai/codex",
    "n",
    "opencode-ai",
]

NPM_TOOLS_FULL: list[str] = []

STOW_PACKAGES: dict[Preset, list[str]] = {
    Preset.MINIMAL: ["shell", "git"],
    Preset.DEV: ["shell", "git", "vim", "tmux", "config", "ai-tools", "misc"],
    Preset.FULL: [
        "shell",
        "git",
        "vim",
        "tmux",
        "config",
        "ai-tools",
        "misc",
        "gui",
    ],
}


@dataclass(frozen=True)
class SetupConfig:
    """Configuration for the setup process."""

    preset: Preset
    dotfiles_repo: str = "https://github.com/sderev/.dotfiles_private.git"
    dotfiles_dir: str = "~/Repos/github.com/sderev/.dotfiles_private"
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

    def get_npm_tools(self) -> list[str]:
        """Return npm tools for current preset (cumulative)."""
        tools = list(NPM_TOOLS_MINIMAL)
        if self.preset in (Preset.DEV, Preset.FULL):
            tools.extend(NPM_TOOLS_DEV)
        if self.preset == Preset.FULL:
            tools.extend(NPM_TOOLS_FULL)
        return tools
