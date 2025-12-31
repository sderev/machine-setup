#!/usr/bin/env bash
set -euo pipefail

PROFILE="${1:-dev}"

if [[ "$(id -u)" -ne 0 ]]; then
	echo "This script must be run as root." >&2
	exit 1
fi

timestamp=$(date +"%Y%m%d%H%M%S")
cp /etc/apt/sources.list "/etc/apt/sources.list.bak.${timestamp}"

cat >/etc/apt/sources.list <<'SOURCES'
deb http://deb.debian.org/debian sid main contrib non-free non-free-firmware
deb-src http://deb.debian.org/debian sid main contrib non-free non-free-firmware
SOURCES

apt-get update
apt-get install -y curl ca-certificates python3-minimal python3-venv

curl -LsSf https://astral.sh/uv/install.sh | sh

export PATH="$HOME/.local/bin:$PATH"

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd "$script_dir"

uv venv
uv pip install -e .
uv run machine-setup --profile "$PROFILE"
