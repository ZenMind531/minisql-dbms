# MiniSQL Windows installer. Keep this file ASCII-only for Windows PowerShell 5.1.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$pythonCommand = $null
$pythonPrefix = @()
foreach ($candidate in @(
    @{ Command = "py"; Prefix = @("-3.11") },
    @{ Command = "python3.11"; Prefix = @() },
    @{ Command = "python"; Prefix = @() }
)) {
    try {
        $command = Get-Command $candidate.Command -ErrorAction Stop
        $version = & $command.Source @($candidate.Prefix) -c `
            "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
        if ($version -eq "3.11") {
            $pythonCommand = $command.Source
            $pythonPrefix = @($candidate.Prefix)
            break
        }
    } catch {
        continue
    }
}

if ($null -eq $pythonCommand) {
    throw "Python 3.11 was not found. Install it from https://www.python.org/downloads/"
}

Write-Host "==> Creating Python 3.11 virtual environment"
& $pythonCommand @pythonPrefix -m venv .venv

Write-Host "==> Installing pytest"
& .\.venv\Scripts\python.exe -m pip install --upgrade pip pytest

Write-Host "==> Installing minidb and minidatagrip commands"
$launcherDir = Join-Path $env:LOCALAPPDATA "MiniDataGrip\bin"
& .\.venv\Scripts\python.exe -m database_system.command_installer `
    --project-root $PSScriptRoot --bin-dir $launcherDir --platform windows

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$pathEntries = @($userPath -split ";" | Where-Object { $_ })
if ($launcherDir -notin $pathEntries) {
    $newUserPath = (($pathEntries + $launcherDir) -join ";")
    [Environment]::SetEnvironmentVariable("Path", $newUserPath, "User")
}

Write-Host ""
Write-Host "MiniDB installation completed. Open a new terminal, then run:"
Write-Host "  minidb          # CLI"
Write-Host "  minidatagrip    # desktop GUI"
Write-Host "Run all tests with:"
Write-Host "  .\.venv\Scripts\python.exe -m pytest tests -v"
