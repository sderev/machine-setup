### Added

* GPG key generation with configurable expiry (default 90 days) via `--generate-gpg-key EMAIL` option
* Descriptive key naming format `machine-setup-{hostname}-{YYYYMMDD}` for both SSH and GPG keys
* `machine-setup keys list` command to show all machine-setup-* keys on GitHub
* `machine-setup keys prune` command to interactively delete machine-setup keys
* `machine-setup keys prune --older-than 30d` option to delete keys older than N days
* `machine-setup keys prune --yes` option to skip confirmation prompt

### Changed

* CLI restructured as a command group with `run` subcommand for full setup
* SSH key titles now use descriptive format instead of static "machine-setup"
