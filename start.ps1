# 从项目虚拟环境启动 MiniDB，并原样转发 CLI 参数。
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path -LiteralPath ".venv\Scripts\python.exe")) {
    throw "未找到 .venv。请先运行：.\install.ps1"
}

& .\.venv\Scripts\python.exe -m database_system.cli.main @args
exit $LASTEXITCODE
