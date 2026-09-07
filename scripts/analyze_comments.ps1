$ErrorActionPreference = 'Stop'
$pythonCommand = Get-Command python.exe -All -ErrorAction SilentlyContinue | Where-Object { $_.Source -notlike '*\WindowsApps\*' } | Select-Object -First 1
$launcherCommand = Get-Command py.exe -ErrorAction SilentlyContinue
$pythonArguments = @()
$pythonPath = if ($pythonCommand) { $pythonCommand.Source } elseif ($launcherCommand) { $pythonArguments = @('-3'); $launcherCommand.Source } else { Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' }
if (-not (Test-Path -LiteralPath $pythonPath)) {
    Write-Error 'Python 3.10+ was not found. Install Python and add it to PATH.'
    exit 1
}
$env:PYTHONIOENCODING = 'utf-8'
Write-Host 'Starting comment analysis...'
& $pythonPath @pythonArguments -u (Join-Path $PSScriptRoot 'analyze_comments.py') @args
exit $LASTEXITCODE
