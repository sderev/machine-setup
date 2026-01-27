"""Tests for CLI interface."""

from click.testing import CliRunner

from machine_setup.main import main


class TestMainCLI:
    """Tests for the main command-line interface."""

    def test_help_output(self):
        """Test that --help works."""
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Personal development environment bootstrap" in result.output
        assert "--verbose" in result.output

    def test_shows_subcommands(self):
        """Test that subcommands are shown in help."""
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert "run" in result.output
        assert "keys" in result.output

    def test_no_subcommand_shows_help(self):
        """Test that invoking without subcommand shows help."""
        runner = CliRunner()
        result = runner.invoke(main, [])
        assert result.exit_code == 0
        assert "run" in result.output


class TestRunSubcommand:
    """Tests for the run subcommand."""

    def test_help_output(self):
        """Test that run --help works."""
        runner = CliRunner()
        result = runner.invoke(main, ["run", "--help"])
        assert result.exit_code == 0
        assert "--preset" in result.output
        assert "--verbose" in result.output

    def test_preset_choices(self):
        """Test that preset choices are displayed."""
        runner = CliRunner()
        result = runner.invoke(main, ["run", "--help"])
        assert "minimal" in result.output
        assert "dev" in result.output
        assert "full" in result.output

    def test_invalid_preset(self):
        """Test that invalid preset is rejected."""
        runner = CliRunner()
        result = runner.invoke(main, ["run", "--preset", "invalid"])
        assert result.exit_code != 0
        assert "Invalid value" in result.output

    def test_all_options_documented(self):
        """Test that all options appear in help."""
        runner = CliRunner()
        result = runner.invoke(main, ["run", "--help"])
        options = [
            "--preset",
            "--dotfiles-repo",
            "--dotfiles-branch",
            "--generate-ssh-key",
            "--generate-gpg-key",
            "--gpg-expiry-days",
            "--skip-packages",
            "--skip-dotfiles",
            "--skip-vim",
            "--skip-windows",
            "--verbose",
        ]
        for option in options:
            assert option in result.output, f"{option} not in help"


class TestKeysSubcommand:
    """Tests for the keys subcommand."""

    def test_help_output(self):
        """Test that keys --help works."""
        runner = CliRunner()
        result = runner.invoke(main, ["keys", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "prune" in result.output

    def test_list_help(self):
        """Test that keys list --help works."""
        runner = CliRunner()
        result = runner.invoke(main, ["keys", "list", "--help"])
        assert result.exit_code == 0
        assert "machine-setup-*" in result.output.lower() or "list" in result.output.lower()

    def test_prune_help(self):
        """Test that keys prune --help works."""
        runner = CliRunner()
        result = runner.invoke(main, ["keys", "prune", "--help"])
        assert result.exit_code == 0
        assert "--older-than" in result.output
        assert "--yes" in result.output
