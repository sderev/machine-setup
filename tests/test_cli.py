"""Tests for CLI interface."""

from click.testing import CliRunner

from machine_setup.main import main


class TestCLI:
    """Tests for the command-line interface."""

    def test_help_output(self):
        """Test that --help works."""
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Automated machine setup" in result.output
        assert "--profile" in result.output
        assert "--verbose" in result.output

    def test_profile_choices(self):
        """Test that profile choices are displayed."""
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert "minimal" in result.output
        assert "dev" in result.output
        assert "full" in result.output

    def test_invalid_profile(self):
        """Test that invalid profile is rejected."""
        runner = CliRunner()
        result = runner.invoke(main, ["--profile", "invalid"])
        assert result.exit_code != 0
        assert "Invalid value" in result.output

    def test_all_options_documented(self):
        """Test that all options appear in help."""
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        options = [
            "--profile",
            "--dotfiles-repo",
            "--dotfiles-branch",
            "--generate-ssh-key",
            "--skip-packages",
            "--skip-dotfiles",
            "--skip-vim",
            "--verbose",
        ]
        for option in options:
            assert option in result.output, f"{option} not in help"
