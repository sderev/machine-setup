#!/usr/bin/env bash
set -euo pipefail

PRESET="dev"
if [[ $# -gt 0 ]]; then
	PRESET="$1"
	shift
fi
extra_args=("$@")

if [[ "$(id -u)" -ne 0 ]]; then
	echo "This script must be run as root (use sudo)." >&2
	exit 1
fi

setup_user="${SUDO_USER:-}"
if [[ -z "$setup_user" || "$setup_user" == "root" ]]; then
	echo "Run this script with sudo from a non-root user." >&2
	exit 1
fi

setup_home=$(getent passwd "$setup_user" | cut -d: -f6)
if [[ -z "$setup_home" ]]; then
	echo "Could not determine home directory for user: $setup_user" >&2
	exit 1
fi

bootstrap_config_dir="${setup_home}/.config/machine-setup"
bootstrap_config_path="${bootstrap_config_dir}/bootstrap.toml"

run_as_user() {
	sudo -u "$setup_user" -H env "PATH=${setup_home}/.local/bin:${PATH}" "$@"
}

toml_escape() {
	local value="$1"
	value="${value//\\/\\\\}"
	value="${value//\"/\\\"}"
	printf '%s' "$value"
}

read_bootstrap_string() {
	local key="$1"
	if [[ ! -f "$bootstrap_config_path" ]]; then
		return 0
	fi
	local value
	value=$(sed -nE "s/^${key}[[:space:]]*=[[:space:]]*\"(.*)\"[[:space:]]*$/\1/p" "$bootstrap_config_path" | tail -n1)
	if [[ -n "$value" ]]; then
		value="${value//\\\"/\"}"
		value="${value//\\\\/\\}"
		printf '%s' "$value"
	fi
}

read_bootstrap_bool() {
	local key="$1"
	if [[ ! -f "$bootstrap_config_path" ]]; then
		return 0
	fi
	sed -nE "s/^${key}[[:space:]]*=[[:space:]]*(true|false)[[:space:]]*$/\1/p" "$bootstrap_config_path" | tail -n1
}

normalize_bool() {
	local raw="${1:-}"
	raw="${raw,,}"
	case "$raw" in
	true | 1 | yes | y) echo "true" ;;
	false | 0 | no | n) echo "false" ;;
	"") echo "" ;;
	*)
		echo "invalid"
		return 1
		;;
	esac
}

write_bootstrap_state() {
	local dotfiles_repo="$1"
	local dotfiles_branch="$2"
	local apply_wslconfig="$3"
	local wslconfig_source_checksum="$4"

	install -d -m 700 -o "$setup_user" -g "$setup_user" "$bootstrap_config_dir"

	local tmp_file
	tmp_file=$(mktemp)
	{
		printf 'dotfiles_repo = "%s"\n' "$(toml_escape "$dotfiles_repo")"
		printf 'dotfiles_branch = "%s"\n' "$(toml_escape "$dotfiles_branch")"
		if [[ -n "$apply_wslconfig" ]]; then
			printf 'apply_wslconfig = %s\n' "$apply_wslconfig"
		fi
		if [[ -n "$wslconfig_source_checksum" ]]; then
			printf 'wslconfig_source_checksum = "%s"\n' "$(toml_escape "$wslconfig_source_checksum")"
		fi
	} >"$tmp_file"

	install -m 600 -o "$setup_user" -g "$setup_user" "$tmp_file" "$bootstrap_config_path"
	rm -f "$tmp_file"
}

configure_apt_sources() {
	# Check if already using sid (sources.list or sources.list.d in list/DEB822 format)
	if grep -q "deb.*sid" /etc/apt/sources.list 2>/dev/null; then
		echo "Already configured for Debian sid (sources.list)"
		return 0
	fi

	if grep -rq "deb.*sid" /etc/apt/sources.list.d/*.list 2>/dev/null; then
		echo "Already configured for Debian sid (sources.list.d/*.list)"
		return 0
	fi

	if grep -rq "Suites:.*sid" /etc/apt/sources.list.d/*.sources 2>/dev/null; then
		echo "Already configured for Debian sid (DEB822 format)"
		return 0
	fi

	echo "Configuring apt sources for Debian sid..."
	timestamp=$(date +"%Y%m%d%H%M%S")

	# Backup existing sources.list if it exists and is not empty
	if [[ -s /etc/apt/sources.list ]]; then
		cp /etc/apt/sources.list "/etc/apt/sources.list.bak.${timestamp}"
		echo "Backed up sources.list to sources.list.bak.${timestamp}"
	fi

	cat >/etc/apt/sources.list <<'SOURCES'
deb http://deb.debian.org/debian sid main contrib non-free non-free-firmware
deb-src http://deb.debian.org/debian sid main contrib non-free non-free-firmware
SOURCES
	echo "apt sources configured for Debian sid"
}

configure_apt_sources

apt-get update
apt-get install -y curl ca-certificates python3-minimal gh

# Authenticate with GitHub early (so prompts happen upfront)
if ! run_as_user gh auth status --hostname github.com >/dev/null 2>&1; then
	run_as_user gh auth login --hostname github.com --git-protocol https --scopes admin:public_key
fi
run_as_user gh auth setup-git

user_uv="${setup_home}/.local/bin/uv"
if [[ ! -x "$user_uv" ]]; then
	run_as_user sh -c "curl -LsSf https://astral.sh/uv/install.sh | sh"
fi

cli_dotfiles_repo=""
cli_dotfiles_branch=""
cli_apply_wslconfig=""
forwarded_args=()

set -- "${extra_args[@]}"
while [[ $# -gt 0 ]]; do
	case "$1" in
	--dotfiles-repo)
		if [[ $# -lt 2 ]]; then
			echo "Missing value for --dotfiles-repo" >&2
			exit 1
		fi
		cli_dotfiles_repo="$2"
		shift 2
		;;
	--dotfiles-repo=*)
		cli_dotfiles_repo="${1#*=}"
		shift
		;;
	--dotfiles-branch)
		if [[ $# -lt 2 ]]; then
			echo "Missing value for --dotfiles-branch" >&2
			exit 1
		fi
		cli_dotfiles_branch="$2"
		shift 2
		;;
	--dotfiles-branch=*)
		cli_dotfiles_branch="${1#*=}"
		shift
		;;
	--apply-wslconfig)
		cli_apply_wslconfig="true"
		shift
		;;
	--no-apply-wslconfig)
		cli_apply_wslconfig="false"
		shift
		;;
	*)
		forwarded_args+=("$1")
		shift
		;;
	esac
done

persisted_dotfiles_repo="$(read_bootstrap_string "dotfiles_repo")"
persisted_dotfiles_branch="$(read_bootstrap_string "dotfiles_branch")"
persisted_apply_wslconfig="$(read_bootstrap_bool "apply_wslconfig")"
persisted_wsl_checksum="$(read_bootstrap_string "wslconfig_source_checksum")"

env_dotfiles_repo="${MACHINE_SETUP_DOTFILES_REPO:-}"
env_dotfiles_branch="${MACHINE_SETUP_DOTFILES_BRANCH:-}"

env_apply_raw="${MACHINE_SETUP_APPLY_WSLCONFIG:-}"
if ! env_apply_wslconfig="$(normalize_bool "$env_apply_raw")"; then
	echo "Invalid MACHINE_SETUP_APPLY_WSLCONFIG value: $env_apply_raw" >&2
	exit 1
fi

dotfiles_repo="${cli_dotfiles_repo:-${env_dotfiles_repo:-$persisted_dotfiles_repo}}"
if [[ -z "$dotfiles_repo" && -t 0 ]]; then
	read -r -p "Dotfiles repo URL (required): " dotfiles_repo
fi
if [[ -z "$dotfiles_repo" ]]; then
	echo "Missing required dotfiles repo." >&2
	echo "Provide --dotfiles-repo, MACHINE_SETUP_DOTFILES_REPO, or ${bootstrap_config_path}." >&2
	exit 1
fi

dotfiles_branch="${cli_dotfiles_branch:-${env_dotfiles_branch:-$persisted_dotfiles_branch}}"
if [[ -z "$dotfiles_branch" ]]; then
	dotfiles_branch="main"
fi

apply_wslconfig_override="${cli_apply_wslconfig:-$env_apply_wslconfig}"
apply_wslconfig="${apply_wslconfig_override:-$persisted_apply_wslconfig}"

write_bootstrap_state "$dotfiles_repo" "$dotfiles_branch" "$apply_wslconfig" "$persisted_wsl_checksum"

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd "$script_dir"

run_as_user "$user_uv" venv --clear
run_as_user "$user_uv" pip install -e .

run_cmd=(
	run_as_user "$user_uv" run machine-setup run
	--preset "$PRESET"
	--dotfiles-repo "$dotfiles_repo"
	--dotfiles-branch "$dotfiles_branch"
)
if [[ "$apply_wslconfig_override" == "true" ]]; then
	run_cmd+=(--apply-wslconfig)
elif [[ "$apply_wslconfig_override" == "false" ]]; then
	run_cmd+=(--no-apply-wslconfig)
fi
run_cmd+=("${forwarded_args[@]}")

"${run_cmd[@]}"
