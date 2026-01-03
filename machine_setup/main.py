"""Main entry point for machine-setup."""

import logging
import sys
import time

import click

from machine_setup.config import Profile, SetupConfig
from machine_setup.dotfiles import clone_dotfiles, stow_dotfiles
from machine_setup.packages import install_packages
from machine_setup.secrets import setup_ssh
from machine_setup.shell import setup_shell
from machine_setup.tools import install_uv_tools
from machine_setup.utils import setup_logging
from machine_setup.vim_setup import setup_vim

logger = logging.getLogger("machine_setup")

TIMING_STEPS = (
    "install_packages",
    "install_uv_tools",
    "clone_dotfiles",
    "stow_dotfiles",
    "setup_vim",
    "setup_shell",
)


def format_duration(seconds: float) -> str:
    """Format timing duration in seconds."""
    return f"{seconds:.1f}s"


def print_timing_report(timings: dict[str, float], total: float) -> None:
    """Print timing report for setup steps."""
    print("=== Timing Report ===")
    for step in TIMING_STEPS:
        print(f"{step}: {format_duration(timings.get(step, 0.0))}")
    print(f"Total: {format_duration(total)}")


@click.command()
@click.option(
    "--profile",
    "-p",
    type=click.Choice([p.value for p in Profile], case_sensitive=False),
    default="dev",
    help="Installation profile (default: dev)",
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
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose output",
)
@click.option(
    "--parallel",
    is_flag=True,
    help="Enable parallel installs for uv tools and stow packages",
)
def main(
    profile: str,
    dotfiles_repo: str,
    dotfiles_branch: str,
    generate_ssh_key: bool,
    skip_packages: bool,
    skip_dotfiles: bool,
    skip_vim: bool,
    verbose: bool,
    parallel: bool,
) -> None:
    """Automated machine setup for Debian development environments."""
    setup_logging(verbose)

    profile_enum = Profile(profile)
    logger.info("Starting machine setup with profile: %s", profile_enum.value)

    config = SetupConfig(
        profile=profile_enum,
        dotfiles_repo=dotfiles_repo,
        dotfiles_branch=dotfiles_branch,
    )

    timings: dict[str, float] = {}
    setup_start = time.perf_counter()

    try:
        if not skip_packages:
            logger.info("=== Installing packages ===")
            step_start = time.perf_counter()
            install_packages(config)
            timings["install_packages"] = time.perf_counter() - step_start

            logger.info("=== Installing uv tools ===")
            step_start = time.perf_counter()
            install_uv_tools(config.get_uv_tools(), parallel=parallel)
            timings["install_uv_tools"] = time.perf_counter() - step_start
        else:
            timings["install_packages"] = 0.0
            timings["install_uv_tools"] = 0.0

        if not skip_dotfiles:
            logger.info("=== Setting up dotfiles ===")
            step_start = time.perf_counter()
            dotfiles_path = clone_dotfiles(config)
            timings["clone_dotfiles"] = time.perf_counter() - step_start

            step_start = time.perf_counter()
            stow_dotfiles(config, dotfiles_path, parallel=parallel)
            timings["stow_dotfiles"] = time.perf_counter() - step_start
        else:
            timings["clone_dotfiles"] = 0.0
            timings["stow_dotfiles"] = 0.0

        if generate_ssh_key:
            logger.info("=== Setting up SSH key ===")
            setup_ssh(generate=generate_ssh_key)

        if not skip_vim:
            logger.info("=== Setting up vim ===")
            step_start = time.perf_counter()
            setup_vim()
            timings["setup_vim"] = time.perf_counter() - step_start
        else:
            timings["setup_vim"] = 0.0

        logger.info("=== Configuring shell ===")
        step_start = time.perf_counter()
        setup_shell()
        timings["setup_shell"] = time.perf_counter() - step_start

        logger.info("=== Setup complete ===")
        total_time = time.perf_counter() - setup_start
        print_timing_report(timings, total_time)

    except Exception as error:
        logger.error("Setup failed: %s", error)
        if verbose:
            raise
        sys.exit(1)


if __name__ == "__main__":
    main()
