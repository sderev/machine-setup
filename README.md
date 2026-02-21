# machine-setup

Bootstrap a Debian sid machine with development environment.

## Prerequisites

```bash
apt-get install -y git
```

## Usage

```bash
git clone https://github.com/sderev/machine-setup.git
cd machine-setup
sudo ./bootstrap.sh [preset] [flags...]
```

### Presets

- `dev` (default): Development tools, no GUI
- `minimal`: Essential CLI for containers
- `full`: Full workstation with GUI

### Flags

| Flag | Description |
|------|-------------|
| `--dotfiles-repo REPO` | GitHub repo for dotfiles (default: sderev/.dotfiles_private) |
| `--dotfiles-branch BRANCH` | Branch for dotfiles repo (default: main) |
| `--generate-ssh-key` | Generate SSH key and add to GitHub |
| `--generate-gpg-key EMAIL` | Generate GPG key with this email and add to GitHub |
| `--gpg-expiry-days N` | GPG key expiry in days (default: 90) |
| `--skip-packages` | Skip package installation |
| `--skip-dotfiles` | Skip dotfiles setup |
| `--skip-vim` | Skip vim plugin installation |
| `--skip-windows` | Skip Windows config (WSL only) |
| `--verbose` | Enable verbose output |

## What it does

1. Configures apt sources to Debian sid
2. Runs `apt-get upgrade`
3. Installs `uv` (Python package manager)
4. Installs apt packages, `uv` tools, npm tools (per preset)
5. Installs Fira Code font (dev/full presets; on WSL installs to Windows per-user fonts)
6. Creates repos directory structure (`~/Repos/github.com/{clone,forks,sderev}/`)
7. Clones and stows dotfiles from `~/Repos/github.com/sderev/.dotfiles_private`
8. Generates the `en_US.UTF-8` locale if needed
9. Sets zsh as default shell; installs vim plugins; creates `ipython-math` environment (dev/full only)

## Key generation

### SSH key

```bash
sudo ./bootstrap.sh dev --generate-ssh-key
```

Generates an ed25519 key (no passphrase) and adds it to GitHub via `gh ssh-key add`.

### GPG key

```bash
sudo ./bootstrap.sh dev --generate-gpg-key user@example.com
```

Generates an ed25519 GPG key (no passphrase) with 90-day expiry and adds it to GitHub.

### Key naming convention

Generated keys use descriptive names: `machine-setup-{hostname}-{YYYYMMDD}`.

Example: `machine-setup-workstation-20260127`

## Key management

The `machine-setup keys` commands help manage keys created by this tool on GitHub.

### List keys

```bash
machine-setup keys list
```

Lists all `machine-setup-*` SSH and GPG keys on your GitHub account.

### Prune keys

```bash
# Interactive deletion
machine-setup keys prune

# Delete keys older than 30 days
machine-setup keys prune --older-than 30d

# Skip confirmation
machine-setup keys prune --older-than 30d --yes
```

### Key lifecycle

* **SSH keys**: SSH keys do not expire. Use `keys prune` to remove old keys when no longer needed.
* **GPG keys**: Expire after 90 days by default (configurable via `--gpg-expiry-days`). Regenerate before expiry or use `keys prune` to clean up.

## Windows configuration (WSL only)

WSL is auto-detected via `/proc/version` and the `WSL_DISTRO_NAME` environment variable. On native Linux, these steps are a no-op.

When running in WSL, the following are applied automatically:

* AutoHotkey keyboard remapping (copied to Windows Startup)
* Google Chrome (installed via `winget`)
* Brave (installed via `winget`)
* Proton Pass (installed via `winget`)
* VLC (installed via `winget`)
* Windows Terminal (installed via `winget`)
* Windows Terminal `settings.json`
* PowerToys (installed via `winget`)
* File Pilot (installed via `winget`, config deployed from dotfiles)
* One-time best-effort taskbar pinning in this order:
  Chrome, Brave, Windows Terminal, Windows Clock, Calculator
  (state file: `%LOCALAPPDATA%\\machine-setup\\taskbar-pinning-v1.done`)
* Fira Code font (installed to the Windows per-user font directory)

Use `--skip-windows` to disable all Windows configuration.
