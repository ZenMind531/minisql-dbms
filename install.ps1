# MiniSQL Windows 环境初始化（PowerShell）
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
    throw "未找到 Python 3.11。请先从 https://www.python.org/downloads/ 安装 Python 3.11。"
}

Write-Host "==> 创建 Python 3.11 虚拟环境"
& $pythonCommand @pythonPrefix -m venv .venv

Write-Host "==> 安装 pytest"
& .\.venv\Scripts\python.exe -m pip install --upgrade pip pytest

Write-Host ""
Write-Host "MiniDB 环境准备完成。启动命令："
Write-Host "  .\start.ps1"
Write-Host "完整测试："
Write-Host "  .\.venv\Scripts\python.exe -m pytest tests -v"
