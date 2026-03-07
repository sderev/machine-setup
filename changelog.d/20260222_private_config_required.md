### Changed

* Setup now requires private dotfiles config at `machine-setup/config.toml` and fails fast when missing or invalid
* Preset package/tool/stow definitions, timezone, and owner namespace now come from private config instead of public hardcoded defaults
* `bootstrap.sh` now persists local bootstrap answers in `~/.config/machine-setup/bootstrap.toml`
* WSL setup now supports dotfiles-driven deployment of `/etc/wsl.conf` and optional host `.wslconfig` with persisted consent and checksum tracking
* `machine-setup run` now falls back to persisted `dotfiles_repo` in local bootstrap state when `--dotfiles-repo` is omitted
* Host `.wslconfig` consent prompting now runs only inside WSL when Windows setup is enabled (not `--skip-windows`), and checksum changes trigger a fresh consent decision unless an explicit override is passed
* Node.js is now bootstrapped automatically before npm tool installation when configured npm tools are non-empty, and private config rejects legacy `nodejs`/`npm` package entries and `n` in npm tool lists
