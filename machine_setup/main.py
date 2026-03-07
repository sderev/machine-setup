"""Main entry point for machine-setup."""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

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
    install_node,
    install_npm_tools,
    install_packages,
    install_quarto,
    install_scc,
    install_uv_tools,
    setup_locale,
    setup_timezone,
)
from machine_setup.keys import keys_cli
from machine_setup.presets import Preset, SetupConfig
from machine_setup.private_config import load_private_config
from machine_setup.secrets import setup_gpg, setup_ssh
from machine_setup.utils import setup_logging
from machine_setup.windows import (
    compute_file_checksum,
    deploy_wsl_conf,
    deploy_wslconfig,
    get_windows_username,
    get_wslconfig_source,
    is_wsl,
    load_bootstrap_state,
    save_bootstrap_state,
    setup_windows_configs,
)

logger = logging.getLogger("machine_setup")

GITHUB_HTTP_RE = re.compile(r"^(?:https?://)?github\.com/([^/]+)/([^/]+)$")
GITHUB_SSH_RE = re.compile(r"^(?:git@github\.com:|ssh://git@github\.com/)([^/]+)/([^/]+)$")
NON_GITHUB_DOTFILES_OWNER = "clone"
NON_GITHUB_DOTFILES_REPO = "dotfiles"
NON_GITHUB_REPO_SEGMENT_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _parse_github_owner_repo(dotfiles_repo: str) -> tuple[str, str] | None:
    """Extract owner/repo when input points to GitHub."""
    parsed = urlparse(dotfiles_repo)
    if parsed.scheme in {"http", "https"} and parsed.hostname == "github.com":
        path_parts = [part for part in parsed.path.split("/") if part]
        if len(path_parts) == 2:
            return path_parts[0], path_parts[1]
        return None

    for pattern in (GITHUB_HTTP_RE, GITHUB_SSH_RE):
        match = pattern.match(dotfiles_repo)
        if match:
            return match.group(1), match.group(2)
    return None


def _derive_non_github_repo_name(dotfiles_repo: str) -> str:
    """Derive deterministic fallback repo directory name for non-GitHub URLs."""
    normalized = dotfiles_repo.strip().rstrip("/")
    if normalized.endswith(".git"):
        normalized = normalized[:-4]

    parsed = urlparse(normalized)
    candidate = ""
    if parsed.scheme and parsed.netloc:
        host = parsed.hostname or ""
        if parsed.port is not None:
            host = f"{host}-{parsed.port}" if host else str(parsed.port)
        path_parts = [part for part in parsed.path.split("/") if part]
        candidate = "-".join([part for part in [host, *path_parts] if part])
    else:
        scp_match = re.match(r"^(?:[^@/]+@)?([^:/]+):(.+)$", normalized)
        if scp_match:
            host = scp_match.group(1)
            path_parts = [part for part in scp_match.group(2).split("/") if part]
            candidate = "-".join([host, *path_parts])
        else:
            candidate = normalized

    sanitized = NON_GITHUB_REPO_SEGMENT_RE.sub("-", candidate).strip(".-")
    if not sanitized or sanitized in {".", ".."}:
        return NON_GITHUB_DOTFILES_REPO
    return sanitized


def _resolve_dotfiles_dir(dotfiles_repo: str, home_dir: Path | None = None) -> str:
    """Resolve local clone path from dotfiles repo URL."""
    normalized = dotfiles_repo.strip().rstrip("/")
    if normalized.endswith(".git"):
        normalized = normalized[:-4]

    owner = NON_GITHUB_DOTFILES_OWNER
    repo_name = NON_GITHUB_DOTFILES_REPO
    is_github_repo = False
    github_owner_repo = _parse_github_owner_repo(normalized)
    if github_owner_repo is not None:
        is_github_repo = True
        owner, repo_name = github_owner_repo
    if not is_github_repo:
        repo_name = _derive_non_github_repo_name(normalized)
        logger.warning(
            "Dotfiles repo is not on GitHub; using fallback clone path under "
            "~/Repos/github.com/%s/%s",
            owner,
            repo_name,
        )

    home = home_dir if home_dir is not None else Path.home()
    if owner in {".", ".."} or repo_name in {".", ".."}:
        raise click.UsageError("Dotfiles repo owner/name must not contain '.' or '..' segments.")

    clone_root = (home / "Repos" / "github.com").resolve()
    clone_target = (clone_root / owner / repo_name).resolve()
    try:
        clone_target.relative_to(clone_root)
    except ValueError as error:
        raise click.UsageError("Dotfiles repo must resolve under ~/Repos/github.com.") from error
    return str(clone_target)


def _resolve_dotfiles_repo(
    dotfiles_repo: str | None,
    *,
    bootstrap_state: dict[str, object] | None = None,
) -> str:
    """Resolve dotfiles repo from CLI or persisted bootstrap state."""
    if isinstance(dotfiles_repo, str):
        normalized = dotfiles_repo.strip()
        if normalized:
            return normalized

    state = bootstrap_state if bootstrap_state is not None else load_bootstrap_state()
    stored_value = state.get("dotfiles_repo")
    if isinstance(stored_value, str):
        normalized = stored_value.strip()
        if normalized:
            logger.info("Using dotfiles repo from bootstrap state")
            return normalized

    raise click.UsageError(
        "Missing required dotfiles repo. Pass --dotfiles-repo or persist "
        "`dotfiles_repo` in ~/.config/machine-setup/bootstrap.toml."
    )


def _resolve_apply_wslconfig_policy(
    dotfiles_path: Path,
    *,
    cli_override: bool | None,
    default_value: bool,
    bootstrap_state: dict[str, object] | None = None,
) -> bool:
    """Resolve whether host `.wslconfig` should be applied and persist decision."""
    source_path = get_wslconfig_source(dotfiles_path)
    source_checksum: str | None = None
    if source_path.exists():
        try:
            source_checksum = compute_file_checksum(source_path)
        except OSError as error:
            logger.warning("Could not compute checksum for %s: %s", source_path, error)

    state = bootstrap_state if bootstrap_state is not None else load_bootstrap_state()
    stored_apply = state.get("apply_wslconfig")
    stored_checksum = state.get("wslconfig_source_checksum")
    persisted_apply = stored_apply if isinstance(stored_apply, bool) else None
    persisted_checksum = stored_checksum if isinstance(stored_checksum, str) else None

    should_prompt = (
        cli_override is None
        and source_checksum is not None
        and (persisted_apply is None or persisted_checksum != source_checksum)
    )

    if cli_override is not None:
        apply_wslconfig = cli_override
    elif should_prompt and sys.stdin.isatty():
        apply_wslconfig = click.confirm(
            "Apply Windows host .wslconfig from private dotfiles?",
            default=default_value,
            show_default=True,
        )
    elif should_prompt:
        apply_wslconfig = default_value
        logger.info(
            "Non-interactive run; using private config default for host .wslconfig: %s",
            apply_wslconfig,
        )
    elif persisted_apply is not None:
        apply_wslconfig = persisted_apply
    else:
        apply_wslconfig = default_value

    state["apply_wslconfig"] = apply_wslconfig
    if source_checksum is not None:
        state["wslconfig_source_checksum"] = source_checksum
    save_bootstrap_state(state)

    return apply_wslconfig


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
    required=False,
    help="Dotfiles git repository URL (falls back to persisted bootstrap state)",
)
@click.option(
    "--dotfiles-branch",
    type=str,
    default="main",
    help="Dotfiles git branch to checkout",
)
@click.option(
    "--apply-wslconfig/--no-apply-wslconfig",
    default=None,
    help="Override Windows host .wslconfig deployment policy",
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
    help="Skip stowing dotfiles",
)
@click.option(
    "--skip-vim",
    is_flag=True,
    help="Skip vim plugin installation",
)
@click.option(
    "--skip-windows",
    is_flag=True,
    help="Skip Windows app/config setup (WSL only)",
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
    dotfiles_repo: str | None,
    dotfiles_branch: str,
    apply_wslconfig: bool | None,
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
    bootstrap_state = load_bootstrap_state()
    dotfiles_repo = _resolve_dotfiles_repo(dotfiles_repo, bootstrap_state=bootstrap_state)
    running_wsl = is_wsl()

    try:
        dotfiles_dir = _resolve_dotfiles_dir(dotfiles_repo)
        logger.info("=== Cloning dotfiles (required) ===")
        dotfiles_path = clone_dotfiles(
            dotfiles_repo=dotfiles_repo,
            dotfiles_dir=dotfiles_dir,
            dotfiles_branch=dotfiles_branch,
        )

        logger.info("=== Loading private config ===")
        private_config = load_private_config(dotfiles_path)

        config = SetupConfig.from_private_config(
            preset=preset_enum,
            private_config=private_config,
            dotfiles_repo=dotfiles_repo,
            dotfiles_dir=str(dotfiles_path),
            dotfiles_branch=dotfiles_branch,
        )
        resolved_apply_wslconfig = False
        if running_wsl and not skip_windows:
            resolved_apply_wslconfig = _resolve_apply_wslconfig_policy(
                dotfiles_path,
                cli_override=apply_wslconfig,
                default_value=private_config.wsl.apply_wslconfig,
                bootstrap_state=bootstrap_state,
            )

        logger.info("=== Configuring timezone ===")
        setup_timezone(private_config.setup.timezone)

        if not skip_packages:
            logger.info("=== Installing packages ===")
            install_packages(config)
            npm_tools = config.get_npm_tools()
            if npm_tools:
                logger.info("=== Installing Node.js ===")
                install_node()
            logger.info("=== Installing uv tools ===")
            install_uv_tools(config.get_uv_tools())
            logger.info("=== Installing npm tools ===")
            install_npm_tools(npm_tools)
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
        create_repos_structure(
            Path(config.home_dir).expanduser(),
            config.repos_owner_namespace,
        )

        if not skip_dotfiles:
            logger.info("=== Stowing dotfiles ===")
            stow_dotfiles(config, dotfiles_path)
            rebuild_bat_cache()
            if config.preset in (Preset.DEV, Preset.FULL):
                setup_scripts_symlink(dotfiles_path, Path(config.home_dir).expanduser())

        if running_wsl and not skip_windows:
            logger.info("=== Setting up Windows apps/configs ===")
            setup_windows_configs(dotfiles_path)

        if running_wsl:
            logger.info("=== Applying WSL configuration files ===")
            deploy_wsl_conf(dotfiles_path)

            if resolved_apply_wslconfig:
                windows_username = get_windows_username()
                if windows_username:
                    changed = deploy_wslconfig(dotfiles_path, windows_username)
                    if changed:
                        logger.info("Host .wslconfig changed. Run `wsl --shutdown` on Windows.")
                else:
                    logger.warning("Could not detect Windows username; skipping host .wslconfig")

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
