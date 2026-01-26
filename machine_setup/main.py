"""Main entry point for machine-setup."""

import logging
import sys
from pathlib import Path

import click

from machine_setup.config import Preset, SetupConfig
from machine_setup.dotfiles import (
    clone_dotfiles,
    create_repos_structure,
    setup_scripts_symlink,
    stow_dotfiles,
)
from machine_setup.ipython_setup import setup_ipython_math_profile
from machine_setup.locale import setup_locale
from machine_setup.npm_tools import install_npm_tools
from machine_setup.packages import install_packages, install_quarto
from machine_setup.secrets import setup_ssh
from machine_setup.shell import setup_shell
from machine_setup.tools import install_claude_code, install_uv_tools
from machine_setup.utils import setup_logging
from machine_setup.vim_setup import setup_vim
from machine_setup.windows import setup_windows_configs

logger = logging.getLogger("machine_setup")


@click.command()
@click.option(
    "--preset",
    "-p",
    type=click.Choice([p.value for p in Preset], case_sensitive=False),
    default="dev",
    help="Installation preset (default: dev)",
)
@click.option(
    "--dotfiles-repo",
    type=str,
    default="https://github.com/sderev/.dotfiles_private.git",
    help="Dotfiles git repository URL",
)
@click.option(
    "--dotfiles-branch",
    type=str,
    default="main",
    help="Dotfiles git branch to checkout",
)
@click.option(
    "--generate-ssh-key",
    is_flag=True,
    help="Generate SSH key and add to GitHub",
)
@click.option(
    "--skip-packages",
    is_flag=True,
    help="Skip package installation",
)
@click.option(
    "--skip-dotfiles",
    is_flag=True,
    help="Skip dotfiles cloning/stowing",
)
@click.option(
    "--skip-vim",
    is_flag=True,
    help="Skip vim plugin installation",
)
@click.option(
    "--skip-windows",
    is_flag=True,
    help="Skip Windows configuration (WSL only)",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose output",
)
def main(
    preset: str,
    dotfiles_repo: str,
    dotfiles_branch: str,
    generate_ssh_key: bool,
    skip_packages: bool,
    skip_dotfiles: bool,
    skip_vim: bool,
    skip_windows: bool,
    verbose: bool,
) -> None:
    """Personal development environment bootstrap."""
    setup_logging(verbose)

    preset_enum = Preset(preset)
    logger.info("Starting machine setup with preset: %s", preset_enum.value)

    config = SetupConfig(
        preset=preset_enum,
        dotfiles_repo=dotfiles_repo,
        dotfiles_branch=dotfiles_branch,
    )

    try:
        if not skip_packages:
            logger.info("=== Installing packages ===")
            install_packages(config)
            logger.info("=== Installing uv tools ===")
            install_uv_tools(config.get_uv_tools())
            logger.info("=== Installing npm tools ===")
            install_npm_tools(config.get_npm_tools())
            if config.preset in (Preset.DEV, Preset.FULL):
                logger.info("=== Installing Claude Code ===")
                install_claude_code()
            if config.preset == Preset.FULL:
                logger.info("=== Installing Quarto ===")
                install_quarto()

        logger.info("=== Creating repos directory structure ===")
        create_repos_structure(Path(config.home_dir).expanduser())

        if not skip_dotfiles:
            logger.info("=== Setting up dotfiles ===")
            dotfiles_path = clone_dotfiles(config)
            stow_dotfiles(config, dotfiles_path)
            if config.preset in (Preset.DEV, Preset.FULL):
                setup_scripts_symlink(dotfiles_path, Path(config.home_dir).expanduser())

            if not skip_windows:
                logger.info("=== Setting up Windows configs ===")
                setup_windows_configs(dotfiles_path)

        if generate_ssh_key:
            logger.info("=== Setting up SSH key ===")
            setup_ssh(generate=generate_ssh_key)

        if not skip_vim:
            logger.info("=== Setting up vim ===")
            setup_vim()

        if config.preset in (Preset.DEV, Preset.FULL):
            logger.info("=== Setting up IPython math profile ===")
            setup_ipython_math_profile()

        logger.info("=== Configuring locale ===")
        setup_locale()

        logger.info("=== Configuring shell ===")
        setup_shell()

        logger.info("=== Setup complete ===")

    except Exception as error:
        logger.error("Setup failed: %s", error)
        if verbose:
            raise
        sys.exit(1)


if __name__ == "__main__":
    main()
