$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'find_python.ps1')
$python = Resolve-ProjectPython
if (-not $python) {
    Write-Error '未找到可用的 Python 3.10+。请安装 Python 并加入 PATH，或设置 RETAIL_PYTHON 指向 python.exe。'
    exit 1
}
$pythonPath = $python.Path
$pythonArguments = $python.Args
$env:PYTHONIOENCODING = 'utf-8'
Write-Host 'Starting comment analysis...'
& $pythonPath @pythonArguments -u (Join-Path $PSScriptRoot 'analyze_comments.py') @args
exit $LASTEXITCODE
