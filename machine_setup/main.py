"""Main entry point for machine-setup."""

import logging
import sys
from pathlib import Path

import click

from machine_setup.app_setup import setup_ipython_math_profile, setup_shell, setup_vim
from machine_setup.dotfiles import (
    clone_dotfiles,
    create_repos_structure,
    rebuild_bat_cache,
    setup_scripts_symlink,
    stow_dotfiles,
)
from machine_setup.installers import (
    install_claude_code,
    install_fira_code,
    install_npm_tools,
    install_packages,
    install_quarto,
    install_scc,
    install_uv_tools,
    setup_locale,
)
from machine_setup.keys import keys_cli
from machine_setup.presets import Preset, SetupConfig
from machine_setup.secrets import setup_gpg, setup_ssh
from machine_setup.utils import setup_logging
from machine_setup.windows import setup_windows_configs

logger = logging.getLogger("machine_setup")


@click.group(invoke_without_command=True)
@click.pass_context
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose output",
)
def main(ctx: click.Context, verbose: bool) -> None:
    """Personal development environment bootstrap."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose

    # If no subcommand, show help
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@main.command(name="run")
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
    "--generate-gpg-key",
    "gpg_email",
    type=str,
    default=None,
    help="Generate GPG key with this email and add to GitHub",
)
@click.option(
    "--gpg-expiry-days",
    type=int,
    default=90,
    help="GPG key expiry in days (default: 90)",
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
@click.pass_context
def run_setup(
    ctx: click.Context,
    preset: str,
    dotfiles_repo: str,
    dotfiles_branch: str,
    generate_ssh_key: bool,
    gpg_email: str | None,
    gpg_expiry_days: int,
    skip_packages: bool,
    skip_dotfiles: bool,
    skip_vim: bool,
    skip_windows: bool,
    verbose: bool,
) -> None:
    """Run the full machine setup."""
    # Use verbose from parent context if not set locally
    verbose = verbose or ctx.obj.get("verbose", False)
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
                logger.info("=== Installing SCC ===")
                install_scc()
                logger.info("=== Installing Fira Code font ===")
                install_fira_code(skip_windows=skip_windows)
            if config.preset == Preset.FULL:
                logger.info("=== Installing Quarto ===")
                install_quarto()

        logger.info("=== Creating repos directory structure ===")
        create_repos_structure(Path(config.home_dir).expanduser())

        if not skip_dotfiles:
            logger.info("=== Setting up dotfiles ===")
            dotfiles_path = clone_dotfiles(config)
            stow_dotfiles(config, dotfiles_path)
            rebuild_bat_cache()
            if config.preset in (Preset.DEV, Preset.FULL):
                setup_scripts_symlink(dotfiles_path, Path(config.home_dir).expanduser())

            if not skip_windows:
                logger.info("=== Setting up Windows configs ===")
                setup_windows_configs(dotfiles_path)

        if generate_ssh_key:
            logger.info("=== Setting up SSH key ===")
            setup_ssh(generate=generate_ssh_key)

        if gpg_email:
            logger.info("=== Setting up GPG key ===")
            setup_gpg(email=gpg_email, expiry_days=gpg_expiry_days)

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


# Add keys subcommand group
main.add_command(keys_cli)


if __name__ == "__main__":
    main()
