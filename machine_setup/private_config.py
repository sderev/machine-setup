"""Private dotfiles configuration loader."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib  # type: ignore[import-not-found]

PRIVATE_CONFIG_RELATIVE_PATH = Path("machine-setup") / "config.toml"
REQUIRED_PRESETS = ("minimal", "dev", "full")
LEGACY_NODE_PACKAGES = frozenset({"nodejs", "npm"})
LEGACY_NODE_NPM_TOOLS = frozenset({"n"})


@dataclass(frozen=True)
class SetupSettings:
    """Setup-related options."""

    timezone: str


@dataclass(frozen=True)
class ReposSettings:
    """Repository directory settings."""

    owner_namespace: str


@dataclass(frozen=True)
class PresetSettings:
    """Per-preset package and tooling lists."""

    packages: list[str]
    uv_tools: list[str]
    npm_tools: list[str]
    stow_packages: list[str]


@dataclass(frozen=True)
class WslSettings:
    """WSL policy options."""

    apply_wslconfig: bool


@dataclass(frozen=True)
class PrivateConfig:
    """Validated private configuration."""

    setup: SetupSettings
    repos: ReposSettings
    presets: dict[str, PresetSettings]
    wsl: WslSettings


def load_private_config(dotfiles_path: Path) -> PrivateConfig:
    """Load and validate private config from the cloned dotfiles repo."""
    config_path = dotfiles_path / PRIVATE_CONFIG_RELATIVE_PATH
    if not config_path.exists():
        raise RuntimeError(
            "Required private config is missing. Expected: "
            f"{config_path} (from your cloned private dotfiles repo)."
        )

    try:
        raw = config_path.read_text(encoding="utf-8")
    except OSError as error:
        raise RuntimeError(f"Failed to read private config at {config_path}: {error}") from error

    try:
        parsed = tomllib.loads(raw)
    except Exception as error:
        raise RuntimeError(f"Invalid TOML in private config {config_path}: {error}") from error

    if not isinstance(parsed, dict):
        raise RuntimeError(f"Invalid private config {config_path}: root must be a TOML table")

    setup_table = _require_table(parsed, "setup", config_path)
    repos_table = _require_table(parsed, "repos", config_path)
    presets_table = _require_table(parsed, "presets", config_path)
    wsl_table = _optional_table(parsed, "wsl", config_path)

    setup = SetupSettings(
        timezone=_require_string(setup_table, "timezone", config_path, "setup"),
    )
    repos = ReposSettings(
        owner_namespace=_require_owner_namespace(repos_table, config_path),
    )

    presets: dict[str, PresetSettings] = {}
    for preset_name in REQUIRED_PRESETS:
        preset_table = _require_table(presets_table, preset_name, config_path, "presets")
        presets[preset_name] = PresetSettings(
            packages=_require_string_list(
                preset_table, "packages", config_path, f"presets.{preset_name}"
            ),
            uv_tools=_require_string_list(
                preset_table, "uv_tools", config_path, f"presets.{preset_name}"
            ),
            npm_tools=_require_string_list(
                preset_table, "npm_tools", config_path, f"presets.{preset_name}"
            ),
            stow_packages=_require_string_list(
                preset_table, "stow_packages", config_path, f"presets.{preset_name}"
            ),
        )
    _validate_node_bootstrap_entries(presets, config_path)

    wsl = WslSettings(
        apply_wslconfig=_optional_bool(
            wsl_table, "apply_wslconfig", config_path, "wsl", default=False
        ),
    )

    return PrivateConfig(setup=setup, repos=repos, presets=presets, wsl=wsl)


def _validate_node_bootstrap_entries(
    presets: dict[str, PresetSettings],
    config_path: Path,
) -> None:
    for preset_name, preset in presets.items():
        legacy_packages = sorted(
            package for package in preset.packages if package in LEGACY_NODE_PACKAGES
        )
        if legacy_packages:
            package_list = ", ".join(f"`{package}`" for package in legacy_packages)
            raise RuntimeError(
                f"Invalid private config {config_path}: "
                f"`presets.{preset_name}.packages` contains legacy Node package entries: "
                f"{package_list}. Remove them from apt packages; Node.js is bootstrapped "
                "automatically when npm tools are configured."
            )

        legacy_npm_tools = sorted(
            tool for tool in preset.npm_tools if tool in LEGACY_NODE_NPM_TOOLS
        )
        if legacy_npm_tools:
            tool_list = ", ".join(f"`{tool}`" for tool in legacy_npm_tools)
            raise RuntimeError(
                f"Invalid private config {config_path}: "
                f"`presets.{preset_name}.npm_tools` contains bootstrap tools: {tool_list}. "
                "Remove them; Node.js bootstrap is handled automatically before npm tool installs."
            )


def _require_table(
    container: dict[str, Any],
    key: str,
    config_path: Path,
    scope: str | None = None,
) -> dict[str, Any]:
    value = container.get(key)
    if not isinstance(value, dict):
        location = key if scope is None else f"{scope}.{key}"
        raise RuntimeError(
            f"Invalid private config {config_path}: `{location}` must be a TOML table"
        )
    return value


def _optional_table(
    container: dict[str, Any],
    key: str,
    config_path: Path,
) -> dict[str, Any] | None:
    if key not in container:
        return None
    value = container[key]
    if not isinstance(value, dict):
        raise RuntimeError(f"Invalid private config {config_path}: `{key}` must be a TOML table")
    return value


def _require_string(
    container: dict[str, Any],
    key: str,
    config_path: Path,
    scope: str,
) -> str:
    value = container.get(key)
    if not isinstance(value, str):
        raise RuntimeError(
            f"Invalid private config {config_path}: `{scope}.{key}` must be a non-empty string"
        )

    normalized = value.strip()
    if not normalized:
        raise RuntimeError(
            f"Invalid private config {config_path}: `{scope}.{key}` must be a non-empty string"
        )
    return normalized


def _require_owner_namespace(container: dict[str, Any], config_path: Path) -> str:
    value = _require_string(container, "owner_namespace", config_path, "repos")
    if value in {".", ".."} or "/" in value or "\\" in value:
        raise RuntimeError(
            f"Invalid private config {config_path}: "
            "`repos.owner_namespace` must be a single directory name"
        )
    return value


def _require_string_list(
    container: dict[str, Any],
    key: str,
    config_path: Path,
    scope: str,
) -> list[str]:
    value = container.get(key)
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise RuntimeError(
            f"Invalid private config {config_path}: `{scope}.{key}` must be a list of strings"
        )

    normalized: list[str] = []
    for item in value:
        cleaned = item.strip()
        if not cleaned:
            raise RuntimeError(
                f"Invalid private config {config_path}: "
                f"`{scope}.{key}` must contain non-empty strings"
            )
        normalized.append(cleaned)

    return normalized


def _optional_bool(
    container: dict[str, Any] | None,
    key: str,
    config_path: Path,
    scope: str,
    *,
    default: bool,
) -> bool:
    if container is None or key not in container:
        return default

    value = container[key]
    if not isinstance(value, bool):
        raise RuntimeError(
            f"Invalid private config {config_path}: `{scope}.{key}` must be a boolean"
        )
    return value
