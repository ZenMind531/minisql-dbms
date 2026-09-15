import os
from pathlib import Path

from database_system.command_installer import install_launchers


def test_install_windows_launchers_into_user_bin(tmp_path: Path) -> None:
    project = tmp_path / "Mini SQL Project"
    project.mkdir()
    bin_dir = tmp_path / "bin"

    installed = install_launchers(project, bin_dir, platform="windows")

    assert installed == (bin_dir / "minidb.cmd", bin_dir / "minidatagrip.cmd")
    assert 'database_system.cli.main' in installed[0].read_text(encoding="utf-8")
    assert 'database_system.gui' in installed[1].read_text(encoding="utf-8")
    assert str(project) in installed[0].read_text(encoding="utf-8")


def test_install_linux_launchers_are_executable(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    bin_dir = tmp_path / "bin"

    installed = install_launchers(project, bin_dir, platform="linux")

    assert installed == (bin_dir / "minidb", bin_dir / "minidatagrip")
    assert installed[0].read_text(encoding="utf-8").startswith("#!/usr/bin/env bash\n")
    if os.name != "nt":
        assert installed[0].stat().st_mode & 0o111
        assert installed[1].stat().st_mode & 0o111
