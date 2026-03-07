"""Tests for main run flow orchestration."""

from pathlib import Path

import click
import pytest
from click.testing import CliRunner

import machine_setup.main as main_module
from machine_setup.main import main
from machine_setup.private_config import (
    PresetSettings,
    PrivateConfig,
    ReposSettings,
    SetupSettings,
    WslSettings,
)


def _private_config() -> PrivateConfig:
    return PrivateConfig(
        setup=SetupSettings(timezone="UTC"),
        repos=ReposSettings(owner_namespace="acme"),
        presets={
            "minimal": PresetSettings(
                packages=["git"],
                uv_tools=[],
                npm_tools=[],
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
        wsl=WslSettings(apply_wslconfig=False),
    )


def _patch_run_side_effects(monkeypatch, *, patch_wsl_policy: bool = True) -> None:
    monkeypatch.setattr("machine_setup.main.install_node", lambda: None)
    monkeypatch.setattr("machine_setup.main.install_uv_tools", lambda *_: None)
    monkeypatch.setattr("machine_setup.main.install_npm_tools", lambda *_: None)
    monkeypatch.setattr("machine_setup.main.install_claude_code", lambda: None)
    monkeypatch.setattr("machine_setup.main.install_scc", lambda: None)
    monkeypatch.setattr("machine_setup.main.install_fira_code", lambda **_: None)
    monkeypatch.setattr("machine_setup.main.install_quarto", lambda: None)
    monkeypatch.setattr("machine_setup.main.create_repos_structure", lambda *_: None)
    monkeypatch.setattr("machine_setup.main.stow_dotfiles", lambda *_: None)
    monkeypatch.setattr("machine_setup.main.rebuild_bat_cache", lambda: None)
    monkeypatch.setattr("machine_setup.main.setup_scripts_symlink", lambda *_: None)
    monkeypatch.setattr("machine_setup.main.setup_windows_configs", lambda *_: None)
    monkeypatch.setattr("machine_setup.main.deploy_wsl_conf", lambda *_: False)
    monkeypatch.setattr("machine_setup.main.deploy_wslconfig", lambda *_: False)
    monkeypatch.setattr("machine_setup.main.get_windows_username", lambda: "TestUser")
    monkeypatch.setattr("machine_setup.main.is_wsl", lambda: False)
    monkeypatch.setattr("machine_setup.main.setup_locale", lambda: None)
    monkeypatch.setattr("machine_setup.main.setup_shell", lambda: None)
    monkeypatch.setattr("machine_setup.main.setup_vim", lambda: None)
    monkeypatch.setattr("machine_setup.main.setup_ipython_math_profile", lambda: None)
    monkeypatch.setattr("machine_setup.main.setup_ssh", lambda **_: None)
    monkeypatch.setattr("machine_setup.main.setup_gpg", lambda **_: None)
    if patch_wsl_policy:
        monkeypatch.setattr(
            "machine_setup.main._resolve_apply_wslconfig_policy",
            lambda *_args, **_kwargs: False,
        )


def test_run_loads_private_config_before_package_install(monkeypatch, tmp_path: Path) -> None:
    """`run` must load private config before package installation."""
    call_order: list[str] = []
    dotfiles_path = tmp_path / ".dotfiles_private"
    dotfiles_path.mkdir()
    private_config = _private_config()

    monkeypatch.setattr(
        "machine_setup.main.clone_dotfiles",
        lambda **_kwargs: call_order.append("clone_dotfiles") or dotfiles_path,
    )
    monkeypatch.setattr(
        "machine_setup.main.load_private_config",
        lambda _dotfiles: call_order.append("load_private_config") or private_config,
    )
    monkeypatch.setattr(
        "machine_setup.main.setup_timezone",
        lambda _timezone: call_order.append("setup_timezone"),
    )
    monkeypatch.setattr(
        "machine_setup.main.install_packages",
        lambda _config: call_order.append("install_packages"),
    )
    _patch_run_side_effects(monkeypatch)

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "run",
            "--preset",
            "minimal",
            "--dotfiles-repo",
            "https://github.com/acme/.dotfiles_private.git",
            "--skip-dotfiles",
            "--skip-windows",
            "--skip-vim",
        ],
    )

    assert result.exit_code == 0
    assert call_order.index("clone_dotfiles") < call_order.index("load_private_config")
    assert call_order.index("load_private_config") < call_order.index("setup_timezone")
    assert call_order.index("setup_timezone") < call_order.index("install_packages")


def test_run_exits_when_private_config_fails(monkeypatch, tmp_path: Path) -> None:
    """`run` should exit before package installation on private config failure."""
    dotfiles_path = tmp_path / ".dotfiles_private"
    dotfiles_path.mkdir()
    install_called = {"value": False}

    def fail_private_config(_dotfiles):
        raise RuntimeError("config missing")

    monkeypatch.setattr("machine_setup.main.clone_dotfiles", lambda **_kwargs: dotfiles_path)
    monkeypatch.setattr("machine_setup.main.load_private_config", fail_private_config)
    monkeypatch.setattr(
        "machine_setup.main.install_packages",
        lambda _config: install_called.__setitem__("value", True),
    )
    _patch_run_side_effects(monkeypatch)

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "run",
            "--preset",
            "minimal",
            "--dotfiles-repo",
            "https://github.com/acme/.dotfiles_private.git",
            "--skip-dotfiles",
            "--skip-windows",
            "--skip-vim",
        ],
    )

    assert result.exit_code == 1
    assert install_called["value"] is False


def test_run_installs_node_before_npm_tools_when_npm_tools_are_configured(
    monkeypatch, tmp_path: Path
) -> None:
    """Node bootstrap should run before npm tool install when npm tools are configured."""
    dotfiles_path = tmp_path / ".dotfiles_private"
    dotfiles_path.mkdir()
    private_config = _private_config()
    private_config.presets["minimal"] = PresetSettings(
        packages=["git"],
        uv_tools=[],
        npm_tools=["opencode-ai"],
        stow_packages=["shell", "git"],
    )
    call_order: list[str] = []

    monkeypatch.setattr("machine_setup.main.clone_dotfiles", lambda **_kwargs: dotfiles_path)
    monkeypatch.setattr("machine_setup.main.load_private_config", lambda _dotfiles: private_config)
    monkeypatch.setattr("machine_setup.main.setup_timezone", lambda _timezone: None)
    _patch_run_side_effects(monkeypatch)
    monkeypatch.setattr(
        "machine_setup.main.install_node", lambda: call_order.append("install_node")
    )
    monkeypatch.setattr(
        "machine_setup.main.install_npm_tools",
        lambda _tools: call_order.append("install_npm_tools"),
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "run",
            "--preset",
            "minimal",
            "--dotfiles-repo",
            "https://github.com/acme/.dotfiles_private.git",
            "--skip-dotfiles",
            "--skip-windows",
            "--skip-vim",
        ],
    )

    assert result.exit_code == 0
    assert call_order == ["install_node", "install_npm_tools"]


def test_run_skips_node_bootstrap_when_npm_tools_are_empty(monkeypatch, tmp_path: Path) -> None:
    """Node bootstrap should be skipped when no npm tools are configured."""
    dotfiles_path = tmp_path / ".dotfiles_private"
    dotfiles_path.mkdir()
    private_config = _private_config()
    npm_install_calls: list[list[str]] = []

    monkeypatch.setattr("machine_setup.main.clone_dotfiles", lambda **_kwargs: dotfiles_path)
    monkeypatch.setattr("machine_setup.main.load_private_config", lambda _dotfiles: private_config)
    monkeypatch.setattr("machine_setup.main.setup_timezone", lambda _timezone: None)
    _patch_run_side_effects(monkeypatch)
    monkeypatch.setattr(
        "machine_setup.main.install_node",
        lambda: (_ for _ in ()).throw(AssertionError("install_node must not be called")),
    )
    monkeypatch.setattr(
        "machine_setup.main.install_npm_tools",
        lambda tools: npm_install_calls.append(list(tools)),
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "run",
            "--preset",
            "minimal",
            "--dotfiles-repo",
            "https://github.com/acme/.dotfiles_private.git",
            "--skip-dotfiles",
            "--skip-windows",
            "--skip-vim",
        ],
    )

    assert result.exit_code == 0
    assert npm_install_calls == [[]]


def test_resolve_apply_wslconfig_policy_reprompts_on_checksum_change(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Checksum changes should re-prompt and refresh persisted state."""
    dotfiles_path = tmp_path / ".dotfiles_private"
    source = dotfiles_path / "machine-setup" / "wsl" / ".wslconfig"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("[wsl2]\nmemory=8GB\n")

    saved_state: dict[str, object] = {}
    confirm_called = {"count": 0}

    monkeypatch.setattr(
        "machine_setup.main.load_bootstrap_state",
        lambda: {"apply_wslconfig": False, "wslconfig_source_checksum": "old-checksum"},
    )
    monkeypatch.setattr(
        "machine_setup.main.save_bootstrap_state",
        lambda state: saved_state.update(state),
    )
    monkeypatch.setattr(
        "machine_setup.main.compute_file_checksum",
        lambda _path: "new-checksum",
    )
    monkeypatch.setattr("machine_setup.main.sys.stdin.isatty", lambda: True)
    monkeypatch.setattr(
        "machine_setup.main.click.confirm",
        lambda *_args, **_kwargs: (
            confirm_called.__setitem__("count", confirm_called["count"] + 1) or True
        ),
    )

    resolved = main_module._resolve_apply_wslconfig_policy(
        dotfiles_path,
        cli_override=None,
        default_value=False,
    )

    assert resolved is True
    assert confirm_called["count"] == 1
    assert saved_state["apply_wslconfig"] is True
    assert saved_state["wslconfig_source_checksum"] == "new-checksum"


def test_run_skips_wsl_policy_resolution_outside_wsl(monkeypatch, tmp_path: Path) -> None:
    """Non-WSL runs must not evaluate `.wslconfig` policy or prompts."""
    dotfiles_path = tmp_path / ".dotfiles_private"
    dotfiles_path.mkdir()
    private_config = _private_config()

    monkeypatch.setattr("machine_setup.main.clone_dotfiles", lambda **_kwargs: dotfiles_path)
    monkeypatch.setattr("machine_setup.main.load_private_config", lambda _dotfiles: private_config)
    monkeypatch.setattr("machine_setup.main.setup_timezone", lambda _timezone: None)
    _patch_run_side_effects(monkeypatch)
    monkeypatch.setattr(
        "machine_setup.main._resolve_apply_wslconfig_policy",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not be called")),
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "run",
            "--preset",
            "minimal",
            "--dotfiles-repo",
            "https://github.com/acme/.dotfiles_private.git",
            "--skip-packages",
            "--skip-dotfiles",
            "--skip-windows",
            "--skip-vim",
        ],
    )

    assert result.exit_code == 0


def test_run_applies_windows_setup_in_wsl_when_dotfiles_are_skipped(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """`--skip-dotfiles` should not suppress Windows setup in WSL."""
    dotfiles_path = tmp_path / ".dotfiles_private"
    dotfiles_path.mkdir()
    private_config = _private_config()
    windows_setup_calls = {"count": 0}

    monkeypatch.setattr("machine_setup.main.clone_dotfiles", lambda **_kwargs: dotfiles_path)
    monkeypatch.setattr("machine_setup.main.load_private_config", lambda _dotfiles: private_config)
    monkeypatch.setattr("machine_setup.main.setup_timezone", lambda _timezone: None)
    _patch_run_side_effects(monkeypatch)
    monkeypatch.setattr("machine_setup.main.is_wsl", lambda: True)
    monkeypatch.setattr(
        "machine_setup.main.setup_windows_configs",
        lambda _dotfiles: windows_setup_calls.__setitem__(
            "count", windows_setup_calls["count"] + 1
        ),
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "run",
            "--preset",
            "minimal",
            "--dotfiles-repo",
            "https://github.com/acme/.dotfiles_private.git",
            "--skip-packages",
            "--skip-dotfiles",
            "--skip-vim",
        ],
    )

    assert result.exit_code == 0
    assert windows_setup_calls["count"] == 1


def test_run_skips_windows_setup_when_skip_windows_is_set(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """`--skip-windows` should skip host setup but still deploy `/etc/wsl.conf` in WSL."""
    dotfiles_path = tmp_path / ".dotfiles_private"
    dotfiles_path.mkdir()
    private_config = _private_config()
    windows_setup_calls = {"count": 0}
    wsl_conf_calls = {"count": 0}

    monkeypatch.setattr("machine_setup.main.clone_dotfiles", lambda **_kwargs: dotfiles_path)
    monkeypatch.setattr("machine_setup.main.load_private_config", lambda _dotfiles: private_config)
    monkeypatch.setattr("machine_setup.main.setup_timezone", lambda _timezone: None)
    _patch_run_side_effects(monkeypatch)
    monkeypatch.setattr("machine_setup.main.is_wsl", lambda: True)
    monkeypatch.setattr(
        "machine_setup.main.setup_windows_configs",
        lambda _dotfiles: windows_setup_calls.__setitem__(
            "count", windows_setup_calls["count"] + 1
        ),
    )
    monkeypatch.setattr(
        "machine_setup.main.deploy_wsl_conf",
        lambda _dotfiles: wsl_conf_calls.__setitem__("count", wsl_conf_calls["count"] + 1) or True,
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "run",
            "--preset",
            "minimal",
            "--dotfiles-repo",
            "https://github.com/acme/.dotfiles_private.git",
            "--skip-packages",
            "--skip-dotfiles",
            "--skip-windows",
            "--skip-vim",
        ],
    )

    assert result.exit_code == 0
    assert windows_setup_calls["count"] == 0
    assert wsl_conf_calls["count"] == 1


def test_run_skips_wsl_policy_resolution_when_skip_windows_is_set(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """`--skip-windows` should bypass `.wslconfig` policy resolution in WSL."""
    dotfiles_path = tmp_path / ".dotfiles_private"
    dotfiles_path.mkdir()
    private_config = _private_config()

    monkeypatch.setattr("machine_setup.main.clone_dotfiles", lambda **_kwargs: dotfiles_path)
    monkeypatch.setattr("machine_setup.main.load_private_config", lambda _dotfiles: private_config)
    monkeypatch.setattr("machine_setup.main.setup_timezone", lambda _timezone: None)
    _patch_run_side_effects(monkeypatch)
    monkeypatch.setattr("machine_setup.main.is_wsl", lambda: True)
    monkeypatch.setattr(
        "machine_setup.main._resolve_apply_wslconfig_policy",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not be called")),
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "run",
            "--preset",
            "minimal",
            "--dotfiles-repo",
            "https://github.com/acme/.dotfiles_private.git",
            "--skip-packages",
            "--skip-dotfiles",
            "--skip-windows",
            "--skip-vim",
        ],
    )

    assert result.exit_code == 0


def test_run_uses_persisted_dotfiles_repo_when_option_missing(monkeypatch, tmp_path: Path) -> None:
    """`run` should fall back to persisted `dotfiles_repo` when option is omitted."""
    dotfiles_path = tmp_path / ".dotfiles_private"
    dotfiles_path.mkdir()
    private_config = _private_config()
    persisted_repo = "https://github.com/acme/.dotfiles_private.git"
    captured_repo = {"value": ""}

    monkeypatch.setattr(
        "machine_setup.main.load_bootstrap_state",
        lambda: {"dotfiles_repo": persisted_repo},
    )
    monkeypatch.setattr(
        "machine_setup.main.clone_dotfiles",
        lambda **kwargs: (
            captured_repo.__setitem__("value", kwargs["dotfiles_repo"]) or dotfiles_path
        ),
    )
    monkeypatch.setattr("machine_setup.main.load_private_config", lambda _dotfiles: private_config)
    monkeypatch.setattr("machine_setup.main.setup_timezone", lambda _timezone: None)
    _patch_run_side_effects(monkeypatch)

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "run",
            "--preset",
            "minimal",
            "--skip-packages",
            "--skip-dotfiles",
            "--skip-windows",
            "--skip-vim",
        ],
    )

    assert result.exit_code == 0
    assert captured_repo["value"] == persisted_repo


def test_run_loads_bootstrap_state_once_when_wsl_policy_is_evaluated(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """`run` should load bootstrap state once and pass it through policy resolution."""
    dotfiles_path = tmp_path / ".dotfiles_private"
    dotfiles_path.mkdir()
    private_config = _private_config()
    persisted_repo = "https://github.com/acme/.dotfiles_private.git"
    load_calls = {"count": 0}

    def _load_state() -> dict[str, object]:
        load_calls["count"] += 1
        return {"dotfiles_repo": persisted_repo, "apply_wslconfig": False}

    monkeypatch.setattr("machine_setup.main.load_bootstrap_state", _load_state)
    monkeypatch.setattr("machine_setup.main.save_bootstrap_state", lambda _state: None)
    monkeypatch.setattr("machine_setup.main.clone_dotfiles", lambda **_kwargs: dotfiles_path)
    monkeypatch.setattr("machine_setup.main.load_private_config", lambda _dotfiles: private_config)
    monkeypatch.setattr("machine_setup.main.setup_timezone", lambda _timezone: None)
    monkeypatch.setattr("machine_setup.main.is_wsl", lambda: True)
    _patch_run_side_effects(monkeypatch, patch_wsl_policy=False)

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "run",
            "--preset",
            "minimal",
            "--skip-packages",
            "--skip-dotfiles",
            "--skip-vim",
        ],
    )

    assert result.exit_code == 0
    assert load_calls["count"] == 1


def test_run_errors_when_dotfiles_repo_is_unresolved(monkeypatch) -> None:
    """`run` should fail when no dotfiles repo can be resolved."""
    monkeypatch.setattr("machine_setup.main.load_bootstrap_state", lambda: {})

    runner = CliRunner()
    result = runner.invoke(main, ["run", "--preset", "minimal"])

    assert result.exit_code != 0
    assert "Missing required dotfiles repo" in result.output


@pytest.mark.parametrize(
    "dotfiles_repo",
    [
        "https://github.com/../dotfiles.git",
        "https://github.com/acme/..",
        "git@github.com:./dotfiles.git",
        "ssh://git@github.com/./dotfiles",
    ],
)
def test_resolve_dotfiles_dir_rejects_dot_path_segments(dotfiles_repo: str) -> None:
    """Owner and repo path segments must reject dot navigation values."""
    with pytest.raises(click.UsageError, match="must not contain"):
        main_module._resolve_dotfiles_dir(dotfiles_repo, home_dir=Path("/home/test"))


def test_resolve_dotfiles_dir_non_github_repo_uses_deterministic_clone_path(caplog) -> None:
    """Non-GitHub repos should use deterministic fallback path and emit warning."""
    with caplog.at_level("WARNING", logger="machine_setup"):
        resolved = main_module._resolve_dotfiles_dir(
            "https://gitlab.example/acme/.dotfiles_private.git",
            home_dir=Path("/home/test"),
        )

    assert resolved == "/home/test/Repos/github.com/clone/gitlab.example-acme-.dotfiles_private"
    assert "Dotfiles repo is not on GitHub" in caplog.text


def test_resolve_dotfiles_dir_github_repo_with_credentials_uses_github_path(caplog) -> None:
    """Credentialed GitHub URLs should still resolve as GitHub owner/repo paths."""
    with caplog.at_level("WARNING", logger="machine_setup"):
        resolved = main_module._resolve_dotfiles_dir(
            "https://token@github.com/acme/.dotfiles_private.git",
            home_dir=Path("/home/test"),
        )

    assert resolved == "/home/test/Repos/github.com/acme/.dotfiles_private"
    assert "Dotfiles repo is not on GitHub" not in caplog.text


def test_resolve_dotfiles_dir_non_github_repo_with_credentials_redacts_userinfo(caplog) -> None:
    """Credentialed non-GitHub URLs must not leak userinfo in clone path or logs."""
    with caplog.at_level("WARNING", logger="machine_setup"):
        resolved = main_module._resolve_dotfiles_dir(
            "https://token@gitlab.example/acme/.dotfiles_private.git",
            home_dir=Path("/home/test"),
        )

    assert resolved == "/home/test/Repos/github.com/clone/gitlab.example-acme-.dotfiles_private"
    assert "token" not in resolved
    assert "token" not in caplog.text


def test_resolve_dotfiles_dir_non_github_fallback_stays_under_clone_root() -> None:
    """Fallback resolution must stay under clone root for non-GitHub paths."""
    resolved = Path(
        main_module._resolve_dotfiles_dir(
            "https://example.com/../../tmp/pwn.git",
            home_dir=Path("/home/test"),
        )
    )
    clone_root = Path("/home/test/Repos/github.com")

    assert resolved.is_relative_to(clone_root)


def test_run_help_matches_skip_windows_readme_text() -> None:
    """CLI help for `--skip-windows` should match README wording."""
    runner = CliRunner()
    result = runner.invoke(main, ["run", "--help"])

    assert result.exit_code == 0
    assert "Skip Windows app/config setup (WSL only)" in result.output
