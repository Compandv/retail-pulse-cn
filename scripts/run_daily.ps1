param([ValidateSet('all', 'market', 'community', 'report')][string]$Only = 'all', [switch]$SkipOpen)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'find_python.ps1')
$python = Resolve-ProjectPython
if (-not $python) {
    Write-Error '未找到可用的 Python 3.10+。请安装 Python 并加入 PATH，或设置 RETAIL_PYTHON 指向 python.exe，再运行每日更新。'
    exit 1
}
$pythonPath = $python.Path
$pythonArguments = $python.Args
$env:PYTHONIOENCODING = 'utf-8'
if (-not $SkipOpen) {
    Write-Host 'Opening saved dashboard first. Refresh the page after data update completes.'
    try {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'start_dashboard.ps1')
        if ($LASTEXITCODE -ne 0) { Write-Warning 'Dashboard could not start. Continuing data update.' }
    } catch { Write-Warning 'Dashboard could not start. Continuing data update.' }
}
& $pythonPath @pythonArguments -u (Join-Path $PSScriptRoot 'update_index.py') --only $Only
$updateExitCode = $LASTEXITCODE
Write-Host ('Update process finished. Exit code: ' + $updateExitCode + '. Logs: work/logs')
exit $updateExitCode
