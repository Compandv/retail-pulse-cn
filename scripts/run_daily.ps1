param([ValidateSet('all', 'market', 'community', 'report')][string]$Only = 'all', [switch]$SkipOpen)
$ErrorActionPreference = 'Stop'
$pythonCommand = Get-Command python.exe -All -ErrorAction SilentlyContinue | Where-Object { $_.Source -notlike '*\WindowsApps\*' } | Select-Object -First 1
$launcherCommand = Get-Command py.exe -ErrorAction SilentlyContinue
$pythonArguments = @()
$pythonPath = if ($pythonCommand) { $pythonCommand.Source } elseif ($launcherCommand) { $pythonArguments = @('-3'); $launcherCommand.Source } else { Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' }
if (-not (Test-Path -LiteralPath $pythonPath)) {
    Write-Error '未找到 Python。请安装 Python 3.10+ 并加入 PATH，再运行每日更新。'
    exit 1
}
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
