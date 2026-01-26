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
sudo ./bootstrap.sh [dev|minimal|full]
```

Additional flags (for example, `--generate-ssh-key`) can follow the preset and are
forwarded to `machine-setup`.

**Presets:**
- `dev` (default): Development tools, no GUI
- `minimal`: Essential CLI for containers
- `full`: Full workstation with GUI

## What it does

1. Configures apt sources to Debian sid
2. Runs `apt-get upgrade`
3. Installs `uv` (Python package manager)
4. Installs apt packages, `uv` tools, npm tools (per preset)
5. Creates repos directory structure (`~/Repos/github.com/{clone,forks,sderev}/`)
6. Clones and stows dotfiles from `~/Repos/github.com/sderev/.dotfiles_private`
7. Generates the `en_US.UTF-8` locale if needed
8. Sets zsh as default shell; installs vim plugins (`--skip-vim` to skip); creates `ipython-math` environment (dev/full only)

## SSH key generation

```bash
sudo ./bootstrap.sh dev --generate-ssh-key
```

Generates an ed25519 key (no passphrase) and adds it to GitHub via `gh ssh-key add`.

To remove the key later:

```bash
gh ssh-key list
gh ssh-key delete <key-id>
```
