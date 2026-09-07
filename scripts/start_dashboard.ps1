$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Write-Host 'Opening saved dashboard only. No data collection or model calls.'
$logDirectory = Join-Path $projectRoot 'work\logs'
New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'node_modules'))) {
    Write-Error '首次使用请在项目目录运行 npm install。'
    exit 1
}
if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    Write-Error '未找到 Node.js/npm。请安装 Node.js 22.13+ 并加入 PATH。'
    exit 1
}
if (-not (Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue)) {
    Write-Host 'Starting dashboard server. Startup log: work/logs/dashboard.log'
    Start-Process -FilePath 'cmd.exe' -ArgumentList '/c', 'npm run dev > work\logs\dashboard.log 2>&1' -WorkingDirectory $projectRoot -WindowStyle Hidden
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        if (Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue) { break }
        Start-Sleep -Milliseconds 500
    }
}
if (-not (Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue)) {
    Write-Error '看板尚未启动，请在项目目录运行 npm run dev 查看具体原因。'
    exit 1
}
Write-Host 'Dashboard ready: http://localhost:3000/ (saved data; check the date on the page).'
Start-Process 'http://localhost:3000/'
