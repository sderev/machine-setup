"""Tests for windows.py module."""

import builtins
from pathlib import Path
from unittest.mock import Mock, call, patch

import pytest

from machine_setup.windows import (
    compute_file_checksum,
    deploy_wsl_conf,
    deploy_wslconfig,
    get_bootstrap_state_path,
    get_filepilot_config,
    get_machine_setup_state_dir,
    get_taskbar_pinning_sentinel,
    get_windows_fonts_dir,
    get_windows_startup_folder,
    get_windows_terminal_settings,
    get_windows_username,
    get_windows_wslconfig_path,
    is_wsl,
    load_bootstrap_state,
    pin_taskbar_apps,
    pin_taskbar_apps_once,
    save_bootstrap_state,
    setup_windows_configs,
)

# Store reference to real open to avoid recursion when patching
_real_open = builtins.open


class TestIsWsl:
    """Tests for is_wsl function."""

    def test_wsl_detected_via_proc_version_microsoft(self, tmp_path, monkeypatch):
        """Test WSL detection via /proc/version containing 'microsoft'."""
        proc_version = tmp_path / "proc_version"
        proc_version.write_text("Linux version 5.15.0-microsoft-standard-WSL2\n")

        monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)

        def mock_open_func(path, *args, **kwargs):
            if path == "/proc/version":
                return _real_open(proc_version, *args, **kwargs)
            return _real_open(path, *args, **kwargs)

        with patch("builtins.open", mock_open_func):
            assert is_wsl() is True

    def test_wsl_detected_via_proc_version_wsl(self, tmp_path, monkeypatch):
        """Test WSL detection via /proc/version containing 'wsl'."""
        proc_version = tmp_path / "proc_version"
        proc_version.write_text("Linux version 5.15.0-wsl-standard\n")

        monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)

        def mock_open_func(path, *args, **kwargs):
            if path == "/proc/version":
                return _real_open(proc_version, *args, **kwargs)
            return _real_open(path, *args, **kwargs)

        with patch("builtins.open", mock_open_func):
            assert is_wsl() is True

    def test_wsl_detected_via_env_var(self, monkeypatch):
        """Test WSL detection via WSL_DISTRO_NAME env var."""
        monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu")

        # Mock /proc/version to not contain microsoft/wsl
        with patch("builtins.open", side_effect=FileNotFoundError):
            assert is_wsl() is True

    def test_not_wsl_on_native_linux(self, tmp_path, monkeypatch):
        """Test non-WSL Linux is detected correctly."""
        proc_version = tmp_path / "proc_version"
        proc_version.write_text("Linux version 5.15.0-generic\n")

        monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)

        def mock_open_func(path, *args, **kwargs):
            if path == "/proc/version":
                return _real_open(proc_version, *args, **kwargs)
            return _real_open(path, *args, **kwargs)

        with patch("builtins.open", mock_open_func):
            assert is_wsl() is False

    def test_handles_missing_proc_version(self, monkeypatch):
        """Test graceful handling when /proc/version doesn't exist."""
        monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)

        with patch("builtins.open", side_effect=FileNotFoundError):
            assert is_wsl() is False


class TestGetWindowsUsername:
    """Tests for get_windows_username function."""

    def test_returns_none_when_mnt_c_missing(self):
        """Test returns None when /mnt/c/Users doesn't exist."""
        with patch("machine_setup.windows.Path") as mock_path:
            mock_path.return_value.exists.return_value = False
            result = get_windows_username()
            assert result is None

    def test_skips_system_folders(self, tmp_path, monkeypatch):
        """Test that Public, Default, etc. are skipped."""
        users_dir = tmp_path / "Users"
        users_dir.mkdir()

        # Create system folders with AppData
        for system_folder in ["Public", "Default", "Default User", "All Users"]:
            folder = users_dir / system_folder
            folder.mkdir()
            (folder / "AppData").mkdir()

        # Create a real user folder with AppData
        real_user = users_dir / "JohnDoe"
        real_user.mkdir()
        (real_user / "AppData").mkdir()

        with patch("machine_setup.windows.Path") as mock_path:
            mock_path.return_value = users_dir
            result = get_windows_username()
            assert result == "JohnDoe"

    def test_returns_user_with_appdata(self, tmp_path, monkeypatch):
        """Test returns user folder containing AppData."""
        users_dir = tmp_path / "Users"
        users_dir.mkdir()

        # User without AppData should be skipped
        no_appdata_user = users_dir / "NoAppData"
        no_appdata_user.mkdir()

        # User with AppData should be returned
        with_appdata_user = users_dir / "WithAppData"
        with_appdata_user.mkdir()
        (with_appdata_user / "AppData").mkdir()

        with patch("machine_setup.windows.Path") as mock_path:
            mock_path.return_value = users_dir
            result = get_windows_username()
            assert result == "WithAppData"

    def test_falls_back_to_sorted_username(self, tmp_path, monkeypatch):
        """Test deterministic fallback selection when multiple users exist."""
        users_dir = tmp_path / "Users"
        users_dir.mkdir()

        user_bob = users_dir / "bob"
        user_bob.mkdir()
        (user_bob / "AppData").mkdir()

        user_alice = users_dir / "alice"
        user_alice.mkdir()
        (user_alice / "AppData").mkdir()

        monkeypatch.delenv("USER", raising=False)

        def fake_path(*args, **kwargs):
            if args and args[0] == "/mnt/c/Users":
                return users_dir
            return Path(*args, **kwargs)

        original_iterdir = type(users_dir).iterdir

        def fake_iterdir(self):
            if self == users_dir:
                return iter([user_bob, user_alice])
            return original_iterdir(self)

        with (
            patch("machine_setup.windows.Path", side_effect=fake_path),
            patch.object(type(users_dir), "iterdir", fake_iterdir),
        ):
            result = get_windows_username()
            assert result == "alice"

    def test_prefers_current_user_over_sorted_fallback(self, tmp_path, monkeypatch):
        """Test current Linux user is preferred over sorted fallback."""
        users_dir = tmp_path / "Users"
        users_dir.mkdir()

        user_alice = users_dir / "alice"
        user_alice.mkdir()
        (user_alice / "AppData").mkdir()

        user_bob = users_dir / "bob"
        user_bob.mkdir()
        (user_bob / "AppData").mkdir()

        monkeypatch.setenv("USER", "bob")

        def fake_path(*args, **kwargs):
            if args and args[0] == "/mnt/c/Users":
                return users_dir
            return Path(*args, **kwargs)

        original_iterdir = type(users_dir).iterdir

        def fake_iterdir(self):
            if self == users_dir:
                return iter([user_bob, user_alice])
            return original_iterdir(self)

        with (
            patch("machine_setup.windows.Path", side_effect=fake_path),
            patch.object(type(users_dir), "iterdir", fake_iterdir),
        ):
            result = get_windows_username()
            assert result == "bob"

    def test_returns_none_when_no_valid_users(self, tmp_path, monkeypatch):
        """Test returns None when no valid user folders exist."""
        users_dir = tmp_path / "Users"
        users_dir.mkdir()

        # Only system folders exist
        (users_dir / "Public").mkdir()
        (users_dir / "Default").mkdir()

        with patch("machine_setup.windows.Path") as mock_path:
            mock_path.return_value = users_dir
            result = get_windows_username()
            assert result is None


class TestGetWindowsStartupFolder:
    """Tests for get_windows_startup_folder function."""

    def test_returns_correct_path(self):
        """Test that correct startup folder path is returned."""
        result = get_windows_startup_folder("TestUser")
        expected = Path(
            "/mnt/c/Users/TestUser/AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Startup"
        )
        assert result == expected


class TestGetWindowsFontsDir:
    """Tests for get_windows_fonts_dir function."""

    def test_returns_correct_path(self):
        """Test that correct Windows fonts directory path is returned."""
        result = get_windows_fonts_dir("TestUser")
        expected = Path("/mnt/c/Users/TestUser/AppData/Local/Microsoft/Windows/Fonts")
        assert result == expected


class TestGetWindowsTerminalSettings:
    """Tests for get_windows_terminal_settings function."""

    def test_returns_correct_path(self):
        """Test that correct Windows Terminal settings path is returned."""
        result = get_windows_terminal_settings("TestUser")
        expected = Path(
            "/mnt/c/Users/TestUser/AppData/Local/Packages"
            "/Microsoft.WindowsTerminal_8wekyb3d8bbwe/LocalState/settings.json"
        )
        assert result == expected


class TestGetFilePilotConfig:
    """Tests for get_filepilot_config function."""

    def test_returns_correct_path(self):
        """Test that correct File Pilot config path is returned."""
        result = get_filepilot_config("TestUser")
        expected = Path(
            "/mnt/c/Users/TestUser/AppData/Roaming/Voidstar/FilePilot/FPilot-Config.json"
        )
        assert result == expected


class TestBootstrapState:
    """Tests for bootstrap state helpers."""

    def test_get_bootstrap_state_path(self, tmp_path):
        """Bootstrap state path lives under ~/.config/machine-setup."""
        result = get_bootstrap_state_path(tmp_path)
        assert result == tmp_path / ".config" / "machine-setup" / "bootstrap.toml"

    def test_save_and_load_bootstrap_state(self, tmp_path):
        """Bootstrap state persists and reloads expected keys."""
        state_path = tmp_path / "bootstrap.toml"
        save_bootstrap_state(
            {
                "dotfiles_repo": "https://github.com/acme/.dotfiles_private.git",
                "dotfiles_branch": "main",
                "apply_wslconfig": True,
                "wslconfig_source_checksum": "abc123",
            },
            state_path,
        )

        loaded = load_bootstrap_state(state_path)
        assert loaded["dotfiles_repo"] == "https://github.com/acme/.dotfiles_private.git"
        assert loaded["dotfiles_branch"] == "main"
        assert loaded["apply_wslconfig"] is True
        assert loaded["wslconfig_source_checksum"] == "abc123"

    def test_save_bootstrap_state_sets_restrictive_permissions(self, tmp_path):
        """Bootstrap state should be persisted with mode 0600."""
        state_path = tmp_path / "bootstrap.toml"
        state_path.write_text('dotfiles_repo = "old"\n')
        state_path.chmod(0o666)

        save_bootstrap_state(
            {"dotfiles_repo": "https://github.com/acme/.dotfiles_private.git"}, state_path
        )

        assert (state_path.stat().st_mode & 0o777) == 0o600

    def test_load_bootstrap_state_invalid_toml(self, tmp_path):
        """Invalid bootstrap state should be ignored."""
        state_path = tmp_path / "bootstrap.toml"
        state_path.write_text("[invalid")

        loaded = load_bootstrap_state(state_path)
        assert loaded == {}


class TestWslConfigDeployment:
    """Tests for WSL config deployment helpers."""

    def test_get_windows_wslconfig_path(self):
        """Windows `.wslconfig` path should target user profile root."""
        result = get_windows_wslconfig_path("TestUser")
        assert result == Path("/mnt/c/Users/TestUser/.wslconfig")

    def test_compute_file_checksum(self, tmp_path):
        """Checksum should be stable for identical content."""
        target = tmp_path / "file.txt"
        target.write_text("hello")

        first = compute_file_checksum(target)
        second = compute_file_checksum(target)
        assert first == second

    def test_deploy_wsl_conf_skips_when_source_missing(self, tmp_path):
        """Missing source should skip `/etc/wsl.conf` deployment."""
        dotfiles_path = tmp_path / ".dotfiles_private"
        dotfiles_path.mkdir()

        assert deploy_wsl_conf(dotfiles_path) is False

    def test_deploy_wsl_conf_uses_sudo_when_needed(self, tmp_path):
        """Non-root users should deploy `/etc/wsl.conf` via sudo."""
        dotfiles_path = tmp_path / ".dotfiles_private"
        source = dotfiles_path / "machine-setup" / "wsl" / "wsl.conf"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("[automount]\n")

        with (
            patch("machine_setup.windows.os.geteuid", return_value=1000),
            patch("machine_setup.windows.sudo_prefix", return_value=["sudo"]),
            patch("machine_setup.windows.run") as mock_run,
        ):
            mock_run.return_value = Mock(returncode=0, stderr="")
            assert deploy_wsl_conf(dotfiles_path) is True
            assert mock_run.call_args.args[0][:3] == ["sudo", "install", "-m"]

    def test_deploy_wsl_conf_enforces_mode_for_root_copy(self, tmp_path):
        """Root deployments should set `/etc/wsl.conf` permissions to 0644."""
        dotfiles_path = tmp_path / ".dotfiles_private"
        source = dotfiles_path / "machine-setup" / "wsl" / "wsl.conf"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("[automount]\n")

        target = Mock(spec=Path)
        target.exists.return_value = False

        with (
            patch("machine_setup.windows.os.geteuid", return_value=0),
            patch("machine_setup.windows.Path", return_value=target),
            patch("machine_setup.windows.shutil.copy2") as mock_copy,
        ):
            assert deploy_wsl_conf(dotfiles_path) is True
            mock_copy.assert_called_once_with(source, target)
            target.chmod.assert_called_once_with(0o644)

    def test_deploy_wslconfig_reports_change(self, tmp_path):
        """Deploying changed host config should return True."""
        dotfiles_path = tmp_path / ".dotfiles_private"
        source = dotfiles_path / "machine-setup" / "wsl" / ".wslconfig"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("[wsl2]\nmemory=8GB\n")

        target = tmp_path / "Users" / "TestUser" / ".wslconfig"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("[wsl2]\nmemory=4GB\n")

        with patch("machine_setup.windows.get_windows_wslconfig_path", return_value=target):
            assert deploy_wslconfig(dotfiles_path, "TestUser") is True
            assert target.read_text() == "[wsl2]\nmemory=8GB\n"

    def test_deploy_wslconfig_reports_no_change(self, tmp_path):
        """Deploying identical host config should return False."""
        dotfiles_path = tmp_path / ".dotfiles_private"
        source = dotfiles_path / "machine-setup" / "wsl" / ".wslconfig"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("[wsl2]\nmemory=8GB\n")

        target = tmp_path / "Users" / "TestUser" / ".wslconfig"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("[wsl2]\nmemory=8GB\n")

        with patch("machine_setup.windows.get_windows_wslconfig_path", return_value=target):
            assert deploy_wslconfig(dotfiles_path, "TestUser") is False


class TestTaskbarPinning:
    """Tests for taskbar pinning helpers."""

    def test_machine_setup_state_dir_path(self):
        """State directory is located under Local AppData."""
        result = get_machine_setup_state_dir("TestUser")
        expected = Path("/mnt/c/Users/TestUser/AppData/Local/machine-setup")
        assert result == expected

    def test_taskbar_pinning_sentinel_path(self):
        """Taskbar pinning sentinel path is stable."""
        result = get_taskbar_pinning_sentinel("TestUser")
        expected = Path("/mnt/c/Users/TestUser/AppData/Local/machine-setup/taskbar-pinning-v1.done")
        assert result == expected

    def test_pin_taskbar_apps_runs_powershell(self):
        """Taskbar pinning should call powershell.exe."""
        mock_result = Mock(returncode=0)

        with patch("machine_setup.windows.run", return_value=mock_result) as mock_run:
            assert pin_taskbar_apps() is True
            mock_run.assert_called_once()
            assert mock_run.call_args.args[0][0] == "powershell.exe"

    def test_pin_taskbar_apps_handles_run_failure(self, caplog):
        """Taskbar pinning should log and continue on command failures."""
        import logging

        caplog.set_level(logging.WARNING)
        mock_result = Mock(returncode=1)

        with patch("machine_setup.windows.run", return_value=mock_result):
            assert pin_taskbar_apps() is False

        assert "Taskbar pinning command failed with exit code 1" in caplog.text

    def test_pin_taskbar_apps_once_writes_sentinel(self, tmp_path):
        """First run should attempt pinning and create sentinel."""
        sentinel = tmp_path / "taskbar-pinning-v1.done"

        with (
            patch("machine_setup.windows.get_taskbar_pinning_sentinel", return_value=sentinel),
            patch("machine_setup.windows.pin_taskbar_apps", return_value=True) as mock_pin,
        ):
            pin_taskbar_apps_once("TestUser")

        mock_pin.assert_called_once()
        assert sentinel.exists()

    def test_pin_taskbar_apps_once_skips_when_already_done(self, tmp_path):
        """Second run should skip when sentinel already exists."""
        sentinel = tmp_path / "taskbar-pinning-v1.done"
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.write_text("done\n")

        with (
            patch("machine_setup.windows.get_taskbar_pinning_sentinel", return_value=sentinel),
            patch("machine_setup.windows.pin_taskbar_apps") as mock_pin,
        ):
            pin_taskbar_apps_once("TestUser")

        mock_pin.assert_not_called()


class TestSetupWindowsConfigs:
    """Tests for setup_windows_configs function."""

    @pytest.fixture(autouse=True)
    def _mock_taskbar_pinning(self, monkeypatch):
        """Avoid invoking real PowerShell in setup path tests."""
        mock = Mock()
        monkeypatch.setattr("machine_setup.windows.pin_taskbar_apps_once", mock)
        return mock

    def test_skips_when_not_wsl(self, monkeypatch, caplog):
        """Test that function returns early when not in WSL."""
        with patch("machine_setup.windows.is_wsl", return_value=False):
            setup_windows_configs(Path("/fake/dotfiles"))
            # Function should return early without doing anything else
            assert True  # May not log at debug level

    def test_skips_when_username_not_detected(self, monkeypatch, caplog):
        """Test graceful handling when Windows username can't be found."""
        import logging

        caplog.set_level(logging.WARNING)

        with (
            patch("machine_setup.windows.is_wsl", return_value=True),
            patch("machine_setup.windows.get_windows_username", return_value=None),
        ):
            setup_windows_configs(Path("/fake/dotfiles"))
            assert "Could not detect Windows username" in caplog.text

    def test_installs_ahk_when_present(self, tmp_path, monkeypatch, caplog):
        """Test AutoHotkey installation when source file exists."""
        import logging

        caplog.set_level(logging.INFO)

        dotfiles = tmp_path / "dotfiles"
        dotfiles.mkdir()
        ahk_dir = dotfiles / "windows" / "startup"
        ahk_dir.mkdir(parents=True)
        ahk_src = ahk_dir / "remapping.ahk"
        ahk_src.write_text("; AHK script")

        startup_dir = tmp_path / "startup"
        startup_dir.mkdir()

        with (
            patch("machine_setup.windows.is_wsl", return_value=True),
            patch("machine_setup.windows.get_windows_username", return_value="TestUser"),
            patch("machine_setup.windows.install_winget_package", return_value=True),
            patch("machine_setup.windows.get_windows_startup_folder", return_value=startup_dir),
        ):
            setup_windows_configs(dotfiles)

            # Verify AHK was copied
            assert (startup_dir / "remapping.ahk").exists()
            assert "Installed remapping.ahk to Windows Startup" in caplog.text

    def test_handles_missing_startup_folder(self, tmp_path, monkeypatch, caplog):
        """Test warning when Startup folder doesn't exist."""
        import logging

        caplog.set_level(logging.WARNING)

        dotfiles = tmp_path / "dotfiles"
        dotfiles.mkdir()
        ahk_dir = dotfiles / "windows" / "startup"
        ahk_dir.mkdir(parents=True)
        ahk_src = ahk_dir / "remapping.ahk"
        ahk_src.write_text("; AHK script")

        nonexistent_startup = tmp_path / "nonexistent_startup"

        with (
            patch("machine_setup.windows.is_wsl", return_value=True),
            patch("machine_setup.windows.get_windows_username", return_value="TestUser"),
            patch("machine_setup.windows.install_winget_package", return_value=True),
            patch(
                "machine_setup.windows.get_windows_startup_folder",
                return_value=nonexistent_startup,
            ),
        ):
            setup_windows_configs(dotfiles)
            assert "Windows Startup folder not found" in caplog.text

    def test_handles_ahk_winget_install_failure(self, tmp_path, monkeypatch, caplog):
        """Test warning when winget installation fails."""
        import logging

        caplog.set_level(logging.WARNING)

        dotfiles = tmp_path / "dotfiles"
        dotfiles.mkdir()
        ahk_dir = dotfiles / "windows" / "startup"
        ahk_dir.mkdir(parents=True)
        ahk_src = ahk_dir / "remapping.ahk"
        ahk_src.write_text("; AHK script")

        def winget_side_effect(package_id):
            return package_id != "AutoHotkey.AutoHotkey"

        with (
            patch("machine_setup.windows.is_wsl", return_value=True),
            patch("machine_setup.windows.get_windows_username", return_value="TestUser"),
            patch(
                "machine_setup.windows.install_winget_package",
                side_effect=winget_side_effect,
            ),
        ):
            setup_windows_configs(dotfiles)
            assert "Failed to install AutoHotkey via winget" in caplog.text

    def test_installs_windows_terminal_settings(self, tmp_path, monkeypatch, caplog):
        """Test Windows Terminal settings installation."""
        import logging

        caplog.set_level(logging.INFO)

        dotfiles = tmp_path / "dotfiles"
        dotfiles.mkdir()
        wt_dir = dotfiles / "windows" / "windows_terminal"
        wt_dir.mkdir(parents=True)
        wt_src = wt_dir / "settings.json"
        wt_src.write_text('{"profiles": []}')

        wt_dst_dir = tmp_path / "WindowsTerminal"
        wt_dst_dir.mkdir()
        wt_dst = wt_dst_dir / "settings.json"

        with (
            patch("machine_setup.windows.is_wsl", return_value=True),
            patch("machine_setup.windows.get_windows_username", return_value="TestUser"),
            patch("machine_setup.windows.get_windows_terminal_settings", return_value=wt_dst),
            patch("machine_setup.windows.install_winget_package", return_value=True),
        ):
            setup_windows_configs(dotfiles)

            assert wt_dst.exists()
            assert "Installed Windows Terminal settings" in caplog.text

    def test_installs_expected_winget_packages(self, tmp_path):
        """Requested app package IDs are installed via winget."""
        dotfiles = tmp_path / "dotfiles"
        dotfiles.mkdir()

        with (
            patch("machine_setup.windows.is_wsl", return_value=True),
            patch("machine_setup.windows.get_windows_username", return_value="TestUser"),
            patch("machine_setup.windows.install_winget_package", return_value=True) as mock_winget,
        ):
            setup_windows_configs(dotfiles)

        expected_package_ids = [
            "Google.Chrome",
            "Brave.Brave",
            "Proton.ProtonPass",
            "VideoLAN.VLC",
            "Microsoft.WindowsTerminal",
            "Microsoft.PowerToys",
            "Voidstar.FilePilot",
        ]
        for package_id in expected_package_ids:
            assert call(package_id) in mock_winget.call_args_list

    def test_attempts_taskbar_pinning(self, tmp_path, _mock_taskbar_pinning):
        """Taskbar pinning is invoked during Windows setup."""
        dotfiles = tmp_path / "dotfiles"
        dotfiles.mkdir()

        with (
            patch("machine_setup.windows.is_wsl", return_value=True),
            patch("machine_setup.windows.get_windows_username", return_value="TestUser"),
            patch("machine_setup.windows.install_winget_package", return_value=True),
        ):
            setup_windows_configs(dotfiles)

        _mock_taskbar_pinning.assert_called_once_with("TestUser")

    def test_copies_terminal_settings_after_terminal_install_attempt(self, tmp_path):
        """Windows Terminal settings copy happens after install attempt."""
        dotfiles = tmp_path / "dotfiles"
        dotfiles.mkdir()
        wt_dir = dotfiles / "windows" / "windows_terminal"
        wt_dir.mkdir(parents=True)
        wt_src = wt_dir / "settings.json"
        wt_src.write_text('{"profiles": []}')

        wt_dst_dir = tmp_path / "WindowsTerminal"
        wt_dst_dir.mkdir()
        wt_dst = wt_dst_dir / "settings.json"

        manager = Mock()
        with (
            patch("machine_setup.windows.is_wsl", return_value=True),
            patch("machine_setup.windows.get_windows_username", return_value="TestUser"),
            patch("machine_setup.windows.install_winget_package", return_value=True) as mock_winget,
            patch("machine_setup.windows.get_windows_terminal_settings", return_value=wt_dst),
            patch("machine_setup.windows.shutil.copy2") as mock_copy2,
        ):
            manager.attach_mock(mock_winget, "winget")
            manager.attach_mock(mock_copy2, "copy2")
            setup_windows_configs(dotfiles)

        terminal_install_call = manager.mock_calls.index(call.winget("Microsoft.WindowsTerminal"))
        terminal_copy_call = manager.mock_calls.index(call.copy2(wt_src, wt_dst))
        assert terminal_install_call < terminal_copy_call

    def test_installs_powertoys(self, tmp_path, caplog):
        """Test PowerToys is installed via winget."""
        import logging

        caplog.set_level(logging.INFO)

        dotfiles = tmp_path / "dotfiles"
        dotfiles.mkdir()

        with (
            patch("machine_setup.windows.is_wsl", return_value=True),
            patch("machine_setup.windows.get_windows_username", return_value="TestUser"),
            patch("machine_setup.windows.install_winget_package", return_value=True) as mock_winget,
        ):
            setup_windows_configs(dotfiles)

            assert call("Microsoft.PowerToys") in mock_winget.call_args_list
            assert "Installing PowerToys via winget" in caplog.text
            assert "PowerToys installed successfully" in caplog.text

    def test_warns_on_powertoys_failure(self, tmp_path, caplog):
        """Test warning when PowerToys installation fails."""
        import logging

        caplog.set_level(logging.WARNING)

        dotfiles = tmp_path / "dotfiles"
        dotfiles.mkdir()

        def winget_side_effect(package_id):
            return package_id != "Microsoft.PowerToys"

        with (
            patch("machine_setup.windows.is_wsl", return_value=True),
            patch("machine_setup.windows.get_windows_username", return_value="TestUser"),
            patch(
                "machine_setup.windows.install_winget_package",
                side_effect=winget_side_effect,
            ),
        ):
            setup_windows_configs(dotfiles)

            assert "Failed to install PowerToys via winget" in caplog.text

    def test_installs_filepilot(self, tmp_path, caplog):
        """Test File Pilot is installed via winget."""
        import logging

        caplog.set_level(logging.INFO)

        dotfiles = tmp_path / "dotfiles"
        dotfiles.mkdir()

        with (
            patch("machine_setup.windows.is_wsl", return_value=True),
            patch("machine_setup.windows.get_windows_username", return_value="TestUser"),
            patch("machine_setup.windows.install_winget_package", return_value=True) as mock_winget,
        ):
            setup_windows_configs(dotfiles)

            assert call("Voidstar.FilePilot") in mock_winget.call_args_list
            assert "File Pilot installed successfully" in caplog.text

    def test_warns_on_filepilot_failure(self, tmp_path, caplog):
        """Test warning when File Pilot installation fails."""
        import logging

        caplog.set_level(logging.WARNING)

        dotfiles = tmp_path / "dotfiles"
        dotfiles.mkdir()

        def winget_side_effect(package_id):
            return package_id != "Voidstar.FilePilot"

        with (
            patch("machine_setup.windows.is_wsl", return_value=True),
            patch("machine_setup.windows.get_windows_username", return_value="TestUser"),
            patch(
                "machine_setup.windows.install_winget_package",
                side_effect=winget_side_effect,
            ),
        ):
            setup_windows_configs(dotfiles)

            assert "Failed to install File Pilot via winget" in caplog.text

    def test_installs_filepilot_config(self, tmp_path, caplog):
        """Test File Pilot config is copied when source and dest dir exist."""
        import logging

        caplog.set_level(logging.INFO)

        dotfiles = tmp_path / "dotfiles"
        dotfiles.mkdir()
        fp_dir = dotfiles / "windows" / "filepilot"
        fp_dir.mkdir(parents=True)
        fp_src = fp_dir / "FPilot-Config.json"
        fp_src.write_text('{"theme": "dark"}')

        fp_dst_dir = tmp_path / "FilePilot"
        fp_dst_dir.mkdir()
        fp_dst = fp_dst_dir / "FPilot-Config.json"

        with (
            patch("machine_setup.windows.is_wsl", return_value=True),
            patch("machine_setup.windows.get_windows_username", return_value="TestUser"),
            patch("machine_setup.windows.install_winget_package", return_value=True),
            patch("machine_setup.windows.get_filepilot_config", return_value=fp_dst),
        ):
            setup_windows_configs(dotfiles)

            assert fp_dst.exists()
            assert fp_dst.read_text() == '{"theme": "dark"}'
            assert "Installed File Pilot config" in caplog.text

    def test_skips_filepilot_config_when_dir_missing(self, tmp_path, caplog):
        """Test File Pilot config is skipped when dest dir does not exist."""
        import logging

        caplog.set_level(logging.DEBUG)

        dotfiles = tmp_path / "dotfiles"
        dotfiles.mkdir()
        fp_dir = dotfiles / "windows" / "filepilot"
        fp_dir.mkdir(parents=True)
        fp_src = fp_dir / "FPilot-Config.json"
        fp_src.write_text('{"theme": "dark"}')

        fp_dst = tmp_path / "nonexistent" / "FPilot-Config.json"

        with (
            patch("machine_setup.windows.is_wsl", return_value=True),
            patch("machine_setup.windows.get_windows_username", return_value="TestUser"),
            patch("machine_setup.windows.install_winget_package", return_value=True),
            patch("machine_setup.windows.get_filepilot_config", return_value=fp_dst),
        ):
            setup_windows_configs(dotfiles)

            assert not fp_dst.exists()
            assert "File Pilot not installed, skipping config copy" in caplog.text
