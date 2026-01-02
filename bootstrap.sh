#!/usr/bin/env bash
set -euo pipefail

PROFILE="${1:-dev}"

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

run_as_user() {
	sudo -u "$setup_user" -H env "PATH=${setup_home}/.local/bin:${PATH}" "$@"
}

# Configure apt sources for Debian sid if not already configured
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
apt-get install -y curl ca-certificates python3-minimal python3-venv

user_uv="${setup_home}/.local/bin/uv"
if [[ ! -x "$user_uv" ]]; then
	run_as_user sh -c "curl -LsSf https://astral.sh/uv/install.sh | sh"
fi

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd "$script_dir"

run_as_user "$user_uv" venv --clear
run_as_user "$user_uv" pip install -e .
run_as_user "$user_uv" run machine-setup --profile "$PROFILE"
