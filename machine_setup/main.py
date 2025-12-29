"""Main entry point for machine-setup."""

import argparse
import logging
import sys

from machine_setup.config import Profile, SetupConfig
from machine_setup.dotfiles import clone_dotfiles, stow_dotfiles
from machine_setup.packages import install_packages
from machine_setup.secrets import setup_secrets
from machine_setup.shell import setup_shell
from machine_setup.utils import setup_logging
from machine_setup.vim_setup import setup_vim

logger = logging.getLogger("machine_setup")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Automated machine setup for Debian sid",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--profile",
        "-p",
        type=str,
        choices=[profile.value for profile in Profile],
        default="dev",
        help="Installation profile (default: dev)",
    )

    parser.add_argument(
        "--dotfiles-repo",
        type=str,
        default="git@github.com:sderev/.dotfiles_private.git",
        help="Dotfiles git repository URL",
    )

    parser.add_argument(
        "--skip-secrets",
        action="store_true",
        help="Skip secrets setup via Proton Pass",
    )

    parser.add_argument(
        "--skip-packages",
        action="store_true",
        help="Skip package installation",
    )

    parser.add_argument(
        "--skip-dotfiles",
        action="store_true",
        help="Skip dotfiles cloning/stowing",
    )

    parser.add_argument(
        "--skip-vim",
        action="store_true",
        help="Skip vim plugin installation",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )

    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    args = parse_args()
    setup_logging(args.verbose)

    profile = Profile(args.profile)
    logger.info("Starting machine setup with profile: %s", profile.value)

    config = SetupConfig(
        profile=profile,
        dotfiles_repo=args.dotfiles_repo,
        skip_secrets=args.skip_secrets,
    )

    try:
        if not args.skip_packages:
            logger.info("=== Installing packages ===")
            install_packages(config)

        if not args.skip_dotfiles:
            logger.info("=== Setting up dotfiles ===")
            dotfiles_path = clone_dotfiles(config)
            stow_dotfiles(config, dotfiles_path)

        if not args.skip_secrets:
            logger.info("=== Setting up secrets ===")
            setup_secrets(args.skip_secrets)

        if not args.skip_vim:
            logger.info("=== Setting up vim ===")
            setup_vim()

        logger.info("=== Configuring shell ===")
        setup_shell()

        logger.info("=== Setup complete ===")
        return 0

    except Exception as error:
        logger.error("Setup failed: %s", error)
        if args.verbose:
            raise
        return 1


if __name__ == "__main__":
    sys.exit(main())
