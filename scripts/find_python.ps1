# Resolve a working Python 3.10+ for the project scripts.
# Order: $env:RETAIL_PYTHON, project .venv, python.exe on PATH (skipping the
# WindowsApps store alias), the py launcher, then the Codex runtime (warned).
function Test-ProjectPython([string]$Path, [string[]]$Arguments = @()) {
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) { return $false }
    try {
        $ok = & $Path @Arguments -c 'import sys; print(sys.version_info >= (3, 10))' 2>$null
        return ($LASTEXITCODE -eq 0 -and "$ok".Trim() -eq 'True')
    } catch { return $false }
}

function Resolve-ProjectPython {
    $projectRoot = Split-Path -Parent $PSScriptRoot
    $candidates = @()
    if ($env:RETAIL_PYTHON) { $candidates += , @{ Path = $env:RETAIL_PYTHON; Args = @(); Source = 'RETAIL_PYTHON' } }
    $candidates += , @{ Path = (Join-Path $projectRoot '.venv\Scripts\python.exe'); Args = @(); Source = '.venv' }
    Get-Command python.exe -All -ErrorAction SilentlyContinue | Where-Object { $_.Source -notlike '*\WindowsApps\*' } |
        ForEach-Object { $candidates += , @{ Path = $_.Source; Args = @(); Source = 'PATH' } }
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) { $candidates += , @{ Path = $launcher.Source; Args = @('-3'); Source = 'py launcher' } }
    $candidates += , @{ Path = (Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'); Args = @(); Source = 'codex-runtime' }

    foreach ($candidate in $candidates) {
        if (-not (Test-ProjectPython $candidate.Path $candidate.Args)) {
            if ($candidate.Source -eq 'RETAIL_PYTHON') { Write-Warning ('RETAIL_PYTHON 不可用或版本低于 3.10，已忽略：' + $candidate.Path) }
            continue
        }
        if ($candidate.Source -eq 'codex-runtime') {
            Write-Warning ('正在使用 Codex 附带的 Python：' + $candidate.Path + '。它可能随该工具更新而消失；建议安装 Python 3.10+，或设置 RETAIL_PYTHON 指向真实 python.exe。')
        }
        return $candidate
    }
    return $null
}
