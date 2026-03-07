# machine-setup

Bootstrap a Debian sid machine with a private, repo-driven development environment.

## Prerequisites

```bash
apt-get install -y git
```

## Private Config Required

`machine-setup` requires a private config file from your cloned dotfiles repo:

```text
<dotfiles-root>/machine-setup/config.toml
```

Expected schema:

```toml
[setup]
timezone = "America/New_York"

[repos]
owner_namespace = "your-github-namespace"

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

[wsl]
apply_wslconfig = false
```

When this file is missing or invalid, setup fails with an actionable error.

Node.js bootstrap policy:

* Do not add `nodejs` or `npm` to preset `packages`.
* Do not add `n` to preset `npm_tools`.
* Node.js is bootstrapped automatically before npm tool installs when `npm_tools` is non-empty.

## Usage

```bash
git clone https://github.com/sderev/machine-setup.git
cd machine-setup
sudo ./bootstrap.sh [preset] [flags...]
```

`bootstrap.sh` can prompt for missing values and persists local answers in:

```text
~/.config/machine-setup/bootstrap.toml
```

`machine-setup run` also uses this state as fallback for `dotfiles_repo` when `--dotfiles-repo` is omitted.

## Presets

* `dev` (default): Development tools, no GUI
* `minimal`: Essential CLI for containers
* `full`: Full workstation with GUI

## Flags

| Flag | Description |
|------|-------------|
| `--dotfiles-repo REPO` | Git repo for private dotfiles (required on first run; then optional with persisted state) |
| `--dotfiles-branch BRANCH` | Branch for dotfiles repo (default: `main`) |
| `--apply-wslconfig` | Force host `.wslconfig` deployment (WSL) |
| `--no-apply-wslconfig` | Force skip host `.wslconfig` deployment (WSL) |
| `--generate-ssh-key` | Generate SSH key and add to GitHub |
| `--generate-gpg-key EMAIL` | Generate GPG key with this email and add to GitHub |
| `--gpg-expiry-days N` | GPG key expiry in days (default: `90`) |
| `--skip-packages` | Skip package installation |
| `--skip-dotfiles` | Skip stowing dotfiles |
| `--skip-vim` | Skip vim plugin installation |
| `--skip-windows` | Skip Windows app/config setup (WSL only) |
| `--verbose` | Enable verbose output |

## What It Does

1. Configures apt sources to Debian sid
2. Runs `apt-get upgrade`
3. Installs `uv` (Python package manager)
4. Clones dotfiles early and loads required private `config.toml`
5. Applies timezone from private config
6. Installs apt packages, `uv` tools, and npm tools (per preset); when npm tools exist, bootstraps Node.js first
7. Installs Fira Code font (dev/full presets; on WSL installs to Windows per-user fonts)
8. Creates repos directory structure (`~/Repos/github.com/{clone,forks,<owner_namespace>}/`)
9. Stows dotfiles packages from private config
10. Generates the `en_US.UTF-8` locale if needed
11. Sets zsh as default shell; installs vim plugins; creates `ipython-math` environment (dev/full)

## Key Generation

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

## Key Management

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

* SSH keys do not expire. Use `keys prune` to remove old keys when no longer needed.
* GPG keys expire after 90 days by default (configurable via `--gpg-expiry-days`).

## WSL Configuration Deployment

When running in WSL:

* If present in dotfiles, `machine-setup/wsl/wsl.conf` is copied to `/etc/wsl.conf`.
* If enabled by policy, `machine-setup/wsl/.wslconfig` is copied to `%UserProfile%\.wslconfig`.
* When `.wslconfig` changes, the tool logs that `wsl --shutdown` is required.

`.wslconfig` deployment policy is resolved as:

1. CLI override (`--apply-wslconfig` / `--no-apply-wslconfig`) if provided.
2. Persisted local consent in `~/.config/machine-setup/bootstrap.toml`.
3. Private config default (`[wsl].apply_wslconfig`) when no persisted value exists.

The local consent is re-prompted when the source `.wslconfig` content checksum changes.
If `--skip-windows` is passed, this `.wslconfig` policy flow is bypassed and host
`.wslconfig` deployment is skipped.

Windows app/config setup currently:

* Installs (via `winget`): AutoHotkey (when startup script exists), Google Chrome, Brave, Proton Pass, VLC, Windows Terminal, PowerToys, File Pilot.
* Copies dotfiles config when sources exist: startup `remapping.ahk`, Windows Terminal `settings.json`, File Pilot `FPilot-Config.json`.
* Runs one-time taskbar pinning for Chrome, Brave, Windows Terminal, Windows Clock, and Calculator.

Use `--skip-windows` to skip only this Windows app/config flow. It also bypasses host
`.wslconfig` policy/deployment, but does not skip WSL distro config deployment to
`/etc/wsl.conf`.
