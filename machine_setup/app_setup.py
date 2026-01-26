"""Application setup.

Post-install configuration: vim plugins, IPython math profile, and shell configuration.
"""

import logging
import os
import pwd
import subprocess
from pathlib import Path
from textwrap import dedent

from machine_setup.utils import command_exists, run, sudo_prefix

logger = logging.getLogger("machine_setup")


# --- Vim setup ---

VIM_PLUG_URL = "https://raw.githubusercontent.com/junegunn/vim-plug/master/plug.vim"
VIM_PLUG_PATH = Path.home() / ".vim" / "autoload" / "plug.vim"


def install_vim_plug() -> None:
    """Install vim-plug if not present."""
    if VIM_PLUG_PATH.exists():
        logger.debug("vim-plug already installed")
        return

    if not command_exists("curl"):
        logger.warning("curl not found, cannot download vim-plug")
        return

    logger.info("Installing vim-plug...")
    VIM_PLUG_PATH.parent.mkdir(parents=True, exist_ok=True)

    run(
        [
            "curl",
            "-fLo",
            str(VIM_PLUG_PATH),
            "--create-dirs",
            VIM_PLUG_URL,
        ]
    )


def install_vim_plugins() -> None:
    """Install vim plugins using vim-plug."""
    if not command_exists("vim"):
        logger.warning("vim not installed, skipping plugin installation")
        return

    install_vim_plug()

    logger.info("Installing vim plugins...")
    run(
        [
            "vim",
            "+PlugInstall --sync",
            "+qa",
        ],
        check=False,
    )

    logger.info("Vim plugins installed")


def setup_vim() -> None:
    """Complete vim setup."""
    install_vim_plugins()

    undo_dir = Path.home() / ".vim" / "undo-dir"
    undo_dir.mkdir(parents=True, exist_ok=True)
    undo_dir.chmod(0o700)


# --- IPython math profile ---

IPYTHON_MATH_DIR = Path.home() / ".local/share/ipython-math"
IPYTHON_MATH_BIN = Path.home() / ".local/bin/ipython-math"

PYPROJECT_TOML = dedent("""\
    [project]
    name = "ipython-math"
    version = "1.0.0"
    requires-python = ">=3.10"
    dependencies = [
        "ipython>=8.0",
        "numpy>=1.20",
        "pandas>=1.3",
        "matplotlib>=3.5",
        "scipy>=1.10",
        "sympy>=1.12",
        "scikit-learn>=1.0",
        "seaborn>=0.12",
    ]
""")

WRAPPER_SCRIPT = dedent("""\
    #!/bin/bash
    cd "$HOME/.local/share/ipython-math"
    exec uv run ipython --profile=math "$@"
""")


def setup_ipython_math_profile() -> None:
    """Set up IPython math profile with uv-managed virtual environment."""
    if not command_exists("uv"):
        logger.warning("uv not found; skipping ipython math profile setup")
        return

    logger.info("Setting up IPython math profile...")

    IPYTHON_MATH_DIR.mkdir(parents=True, exist_ok=True)

    pyproject_path = IPYTHON_MATH_DIR / "pyproject.toml"
    if not pyproject_path.exists():
        pyproject_path.write_text(PYPROJECT_TOML)
        logger.info("Created %s", pyproject_path)

    logger.info("Installing math packages with uv...")
    result = subprocess.run(
        ["uv", "sync"],
        cwd=IPYTHON_MATH_DIR,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.warning("Failed to sync ipython-math environment: %s", result.stderr)
        return

    IPYTHON_MATH_BIN.parent.mkdir(parents=True, exist_ok=True)
    IPYTHON_MATH_BIN.write_text(WRAPPER_SCRIPT)
    IPYTHON_MATH_BIN.chmod(0o755)
    logger.info("Created wrapper script %s", IPYTHON_MATH_BIN)

    logger.info("IPython math profile setup complete")
    logger.info("Use 'ipython-math' to start IPython with math packages")


# --- Shell configuration ---


def get_current_shell() -> str:
    """Get current user's default shell."""
    try:
        return pwd.getpwuid(os.getuid()).pw_shell
    except KeyError:
        return os.environ.get("SHELL", "/bin/bash")


def get_zsh_path() -> str | None:
    """Get path to zsh binary."""
    result = run(["which", "zsh"], check=False, capture=True)
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def set_default_shell_zsh() -> None:
    """Set zsh as the default shell for current user."""
    current_shell = get_current_shell()

    if "zsh" in current_shell:
        logger.info("zsh is already the default shell")
        return

    zsh_path = get_zsh_path()
    if not zsh_path:
        logger.error("zsh not found in PATH")
        return

    shells_file = Path("/etc/shells")
    if shells_file.exists():
        shells_content = shells_file.read_text()
        if zsh_path not in shells_content:
            logger.info("Adding %s to /etc/shells", zsh_path)
            sudo = sudo_prefix()
            run([*sudo, "sh", "-c", 'printf "%s\\n" "$1" >> /etc/shells', "_", zsh_path])

    logger.info("Setting default shell to zsh...")
    username = pwd.getpwuid(os.getuid()).pw_name
    sudo = sudo_prefix()
    run([*sudo, "chsh", "-s", zsh_path, username])

    logger.info("Default shell changed to zsh (effective on next login)")


def setup_shell() -> None:
    """Complete shell setup."""
    if command_exists("zsh"):
        set_default_shell_zsh()
    else:
        logger.warning("zsh not installed, cannot set as default shell")
