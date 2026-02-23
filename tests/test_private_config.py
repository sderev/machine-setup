"""Tests for private_config module."""

from pathlib import Path

import pytest

from machine_setup.private_config import load_private_config


def _write_config(dotfiles_path: Path, content: str) -> Path:
    config_path = dotfiles_path / "machine-setup" / "config.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(content, encoding="utf-8")
    return config_path


def test_load_private_config_success(tmp_path: Path) -> None:
    """Private config is loaded from dotfiles path."""
    dotfiles_path = tmp_path / ".dotfiles_private"
    _write_config(
        dotfiles_path,
        """
[setup]
timezone = "Europe/Paris"

[repos]
owner_namespace = "acme"

[presets.minimal]
packages = ["git"]
uv_tools = []
npm_tools = []
stow_packages = ["shell", "git"]

[presets.dev]
packages = ["gcc"]
uv_tools = ["ty"]
npm_tools = ["opencode-ai"]
stow_packages = ["shell", "git", "vim"]

[presets.full]
packages = ["texlive"]
uv_tools = ["wslshot"]
npm_tools = ["@openai/codex"]
stow_packages = ["shell", "git", "vim", "gui"]

[wsl]
apply_wslconfig = true
""".strip(),
    )

    config = load_private_config(dotfiles_path)

    assert config.setup.timezone == "Europe/Paris"
    assert config.repos.owner_namespace == "acme"
    assert config.presets["minimal"].packages == ["git"]
    assert config.presets["full"].npm_tools == ["@openai/codex"]
    assert config.wsl.apply_wslconfig is True


def test_load_private_config_defaults_wsl_apply_to_false(tmp_path: Path) -> None:
    """Missing `[wsl]` table should default `apply_wslconfig` to False."""
    dotfiles_path = tmp_path / ".dotfiles_private"
    _write_config(
        dotfiles_path,
        """
[setup]
timezone = "UTC"

[repos]
owner_namespace = "acme"

[presets.minimal]
packages = []
uv_tools = []
npm_tools = []
stow_packages = []

[presets.dev]
packages = []
uv_tools = []
npm_tools = []
stow_packages = []

[presets.full]
packages = []
uv_tools = []
npm_tools = []
stow_packages = []
""".strip(),
    )

    config = load_private_config(dotfiles_path)

    assert config.wsl.apply_wslconfig is False


def test_load_private_config_missing_file(tmp_path: Path) -> None:
    """Missing private config should fail with actionable error."""
    dotfiles_path = tmp_path / ".dotfiles_private"
    dotfiles_path.mkdir()

    with pytest.raises(RuntimeError, match="Required private config is missing"):
        load_private_config(dotfiles_path)


def test_load_private_config_invalid_toml(tmp_path: Path) -> None:
    """Invalid TOML should fail."""
    dotfiles_path = tmp_path / ".dotfiles_private"
    _write_config(dotfiles_path, "[setup\n")

    with pytest.raises(RuntimeError, match="Invalid TOML"):
        load_private_config(dotfiles_path)


def test_load_private_config_missing_required_preset(tmp_path: Path) -> None:
    """All preset sections are required."""
    dotfiles_path = tmp_path / ".dotfiles_private"
    _write_config(
        dotfiles_path,
        """
[setup]
timezone = "UTC"

[repos]
owner_namespace = "acme"

[presets.minimal]
packages = []
uv_tools = []
npm_tools = []
stow_packages = []
""".strip(),
    )

    with pytest.raises(RuntimeError, match="presets.dev"):
        load_private_config(dotfiles_path)


def test_load_private_config_rejects_non_string_lists(tmp_path: Path) -> None:
    """Preset lists must contain strings only."""
    dotfiles_path = tmp_path / ".dotfiles_private"
    _write_config(
        dotfiles_path,
        """
[setup]
timezone = "UTC"

[repos]
owner_namespace = "acme"

[presets.minimal]
packages = [1]
uv_tools = []
npm_tools = []
stow_packages = []

[presets.dev]
packages = []
uv_tools = []
npm_tools = []
stow_packages = []

[presets.full]
packages = []
uv_tools = []
npm_tools = []
stow_packages = []
""".strip(),
    )

    with pytest.raises(RuntimeError, match="list of strings"):
        load_private_config(dotfiles_path)


@pytest.mark.parametrize("legacy_package", ["nodejs", "npm"])
def test_load_private_config_rejects_legacy_node_packages(
    tmp_path: Path,
    legacy_package: str,
) -> None:
    """Legacy Node apt packages must not be configured in private presets."""
    dotfiles_path = tmp_path / ".dotfiles_private"
    _write_config(
        dotfiles_path,
        f"""
[setup]
timezone = "UTC"

[repos]
owner_namespace = "acme"

[presets.minimal]
packages = ["{legacy_package}"]
uv_tools = []
npm_tools = []
stow_packages = []

[presets.dev]
packages = []
uv_tools = []
npm_tools = []
stow_packages = []

[presets.full]
packages = []
uv_tools = []
npm_tools = []
stow_packages = []
""".strip(),
    )

    with pytest.raises(RuntimeError, match="legacy Node package entries"):
        load_private_config(dotfiles_path)


def test_load_private_config_rejects_n_bootstrap_tool(tmp_path: Path) -> None:
    """Legacy `n` bootstrap tool must not be configured in npm tools."""
    dotfiles_path = tmp_path / ".dotfiles_private"
    _write_config(
        dotfiles_path,
        """
[setup]
timezone = "UTC"

[repos]
owner_namespace = "acme"

[presets.minimal]
packages = []
uv_tools = []
npm_tools = ["n"]
stow_packages = []

[presets.dev]
packages = []
uv_tools = []
npm_tools = []
stow_packages = []

[presets.full]
packages = []
uv_tools = []
npm_tools = []
stow_packages = []
""".strip(),
    )

    with pytest.raises(RuntimeError, match="contains bootstrap tools"):
        load_private_config(dotfiles_path)


@pytest.mark.parametrize("list_key", ["packages", "uv_tools", "npm_tools", "stow_packages"])
@pytest.mark.parametrize("invalid_value", ['[""]', '["   "]'])
def test_load_private_config_rejects_empty_string_list_entries(
    tmp_path: Path, list_key: str, invalid_value: str
) -> None:
    """Preset lists must not contain empty string entries."""
    dotfiles_path = tmp_path / ".dotfiles_private"
    values = {
        "packages": "[]",
        "uv_tools": "[]",
        "npm_tools": "[]",
        "stow_packages": "[]",
    }
    values[list_key] = invalid_value

    _write_config(
        dotfiles_path,
        f"""
[setup]
timezone = "UTC"

[repos]
owner_namespace = "acme"

[presets.minimal]
packages = {values["packages"]}
uv_tools = {values["uv_tools"]}
npm_tools = {values["npm_tools"]}
stow_packages = {values["stow_packages"]}

[presets.dev]
packages = []
uv_tools = []
npm_tools = []
stow_packages = []

[presets.full]
packages = []
uv_tools = []
npm_tools = []
stow_packages = []
""".strip(),
    )

    with pytest.raises(RuntimeError, match="contain non-empty strings"):
        load_private_config(dotfiles_path)


def test_load_private_config_trims_whitespace_in_string_values(tmp_path: Path) -> None:
    """String values are normalized during validation."""
    dotfiles_path = tmp_path / ".dotfiles_private"
    _write_config(
        dotfiles_path,
        """
[setup]
timezone = "  Europe/Paris  "

[repos]
owner_namespace = "  acme  "

[presets.minimal]
packages = [" git "]
uv_tools = ["  ruff"]
npm_tools = ["@openai/codex  "]
stow_packages = [" shell "]

[presets.dev]
packages = []
uv_tools = []
npm_tools = []
stow_packages = []

[presets.full]
packages = []
uv_tools = []
npm_tools = []
stow_packages = []
""".strip(),
    )

    config = load_private_config(dotfiles_path)

    assert config.setup.timezone == "Europe/Paris"
    assert config.repos.owner_namespace == "acme"
    assert config.presets["minimal"].packages == ["git"]
    assert config.presets["minimal"].uv_tools == ["ruff"]
    assert config.presets["minimal"].npm_tools == ["@openai/codex"]
    assert config.presets["minimal"].stow_packages == ["shell"]


@pytest.mark.parametrize("owner_namespace", ["acme/team", "acme\\team", ".", ".."])
def test_load_private_config_rejects_invalid_owner_namespace(
    tmp_path: Path,
    owner_namespace: str,
) -> None:
    """Owner namespace must be exactly one directory name."""
    owner_namespace_toml = owner_namespace.replace("\\", "\\\\")
    dotfiles_path = tmp_path / ".dotfiles_private"
    _write_config(
        dotfiles_path,
        f"""
[setup]
timezone = "UTC"

[repos]
owner_namespace = "{owner_namespace_toml}"

[presets.minimal]
packages = []
uv_tools = []
npm_tools = []
stow_packages = []

[presets.dev]
packages = []
uv_tools = []
npm_tools = []
stow_packages = []

[presets.full]
packages = []
uv_tools = []
npm_tools = []
stow_packages = []
""".strip(),
    )

    with pytest.raises(RuntimeError, match="repos.owner_namespace"):
        load_private_config(dotfiles_path)
