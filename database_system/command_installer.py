from __future__ import annotations

import argparse
import os
from pathlib import Path
import shlex


def install_launchers(project_root: str | Path, bin_dir: str | Path,
                      platform: str) -> tuple[Path, Path]:
    project = Path(project_root).resolve()
    destination = Path(bin_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    if platform == "windows":
        cli = destination / "minidb.cmd"
        gui = destination / "minidatagrip.cmd"
        python = project / ".venv" / "Scripts" / "python.exe"
        pythonw = project / ".venv" / "Scripts" / "pythonw.exe"
        cli.write_text(_windows_launcher(project, python, "database_system.cli.main"),
                       encoding="utf-8")
        gui.write_text(_windows_launcher(project, pythonw, "database_system.gui", detach=True),
                       encoding="utf-8")
        return cli, gui
    if platform == "linux":
        cli = destination / "minidb"
        gui = destination / "minidatagrip"
        python = project / ".venv" / "bin" / "python"
        cli.write_text(_linux_launcher(project, python, "database_system.cli.main"),
                       encoding="utf-8", newline="\n")
        gui.write_text(_linux_launcher(project, python, "database_system.gui"),
                       encoding="utf-8", newline="\n")
        cli.chmod(cli.stat().st_mode | 0o755)
        gui.chmod(gui.stat().st_mode | 0o755)
        return cli, gui
    raise ValueError(f"unsupported platform: {platform}")


def _windows_launcher(project: Path, python: Path, module: str,
                      detach: bool = False) -> str:
    command = f'start "" "{python}"' if detach else f'"{python}"'
    return (
        "@echo off\n"
        f'pushd "{project}"\n'
        f"{command} -m {module} %*\n"
        "set \"_MINIDB_EXIT=%ERRORLEVEL%\"\n"
        "popd\n"
        "exit /b %_MINIDB_EXIT%\n"
    )


def _linux_launcher(project: Path, python: Path, module: str) -> str:
    return (
        "#!/usr/bin/env bash\n"
        "set -e\n"
        f"cd {shlex.quote(str(project))}\n"
        f"exec {shlex.quote(str(python))} -m {module} \"$@\"\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Install MiniDB user commands")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--bin-dir", required=True)
    parser.add_argument("--platform", choices=("windows", "linux"), required=True)
    args = parser.parse_args()
    for path in install_launchers(args.project_root, args.bin_dir, args.platform):
        print(path)


if __name__ == "__main__":
    main()
