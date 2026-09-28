# Run by the Windows scheduled task: pull from GitHub, update stale modules,
# push the data back, then show a toast.
param([switch]$FailuresOnly, [switch]$NoSync)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$summaryPath = Join-Path $projectRoot 'work\logs\last-run.json'
# The task runs in a hidden window: keep a transcript so any error can be read later.
$transcript = Join-Path $projectRoot ("work\logs\scheduled-{0:yyyyMMdd-HHmmss}.log" -f (Get-Date))
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $transcript) | Out-Null
Start-Transcript -LiteralPath $transcript | Out-Null
trap { Write-Output ("未处理的错误：" + $_.Exception.Message + " @ " + $_.InvocationInfo.PositionMessage); Stop-Transcript | Out-Null; exit 2 }

function Show-Toast([string]$Title, [string]$Body, [string]$OpenPath) {
    try {
        [void][Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]
        [void][Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime]
        $esc = { param($s) [System.Security.SecurityElement]::Escape($s) }
        $launch = if ($OpenPath -and (Test-Path -LiteralPath $OpenPath)) { ' activationType="protocol" launch="' + (& $esc ([Uri]$OpenPath).AbsoluteUri) + '"' } else { '' }
        $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
        $xml.LoadXml("<toast$launch><visual><binding template=`"ToastGeneric`"><text>$(& $esc $Title)</text><text>$(& $esc $Body)</text></binding></visual></toast>")
        # Windows PowerShell's registered app id, so no extra app registration is needed.
        $appId = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show([Windows.UI.Notifications.ToastNotification]::new($xml))
    } catch {
        Write-Warning ('无法显示系统通知：' + $_.Exception.Message)
    }
}

. (Join-Path $PSScriptRoot 'find_python.ps1')
$python = Resolve-ProjectPython 3>$null
if (-not $python) {
    Show-Toast '散户温度计：定时更新未运行' '找不到可用的 Python 3.10+。请安装 Python，或设置 RETAIL_PYTHON。' $null
    Stop-Transcript | Out-Null
    exit 1
}
$env:PYTHONIOENCODING = 'utf-8'
. (Join-Path $PSScriptRoot 'sync_data.ps1')
$syncNotes = @()
if (-not $NoSync) { $syncNotes += Sync-DataPull }
if (Test-Path -LiteralPath $summaryPath) { Remove-Item -LiteralPath $summaryPath -Force }
# Windows PowerShell 5.1 turns a native program's stderr into errors, and under 'Stop'
# the first stderr line (e.g. a partial-failure note) would abort this script before
# the push and the toast. Run Python with 'Continue' and rely on its exit code.
$ErrorActionPreference = 'Continue'
& $python.Path @($python.Args) -u (Join-Path $PSScriptRoot 'update_index.py') --if-stale *> $null
$exitCode = $LASTEXITCODE
$ErrorActionPreference = 'Stop'

$summary = $null
if (Test-Path -LiteralPath $summaryPath) { $summary = Get-Content -LiteralPath $summaryPath -Raw -Encoding UTF8 | ConvertFrom-Json }
$log = if ($summary) { $summary.log } else { $null }
$day = if ($summary -and $summary.tradeDate) { $summary.tradeDate } else { '最近交易日' }
$warning = if ($summary -and $summary.calendarWarning) { ' ' + $summary.calendarWarning } else { '' }
if (-not $NoSync) { $syncNotes += Sync-DataPush $day }
$syncNote = ($syncNotes | Where-Object { $_ }) -join '；'
if ($syncNote) { $warning += ' 同步：' + $syncNote + '。' }

if (-not $summary) {
    Show-Toast '散户温度计：定时更新异常' ("更新程序没有写出运行结果（退出码 $exitCode）。请查看 work\logs。") (Join-Path $projectRoot 'work\logs')
} elseif ($summary.status -eq 'ok') {
    if (-not $FailuresOnly -or $warning) { Show-Toast "散户温度计：$day 已更新" ("$($summary.succeeded) 个模块更新成功。$warning").Trim() $log }
} elseif ($summary.status -eq 'skipped') {
    if ($warning) { Show-Toast '散户温度计：提醒' $warning.Trim() $log }
} elseif ($summary.status -in 'partial', 'failed') {
    $detail = ($summary.failures | ForEach-Object { ($_ -split '：', 2)[0] }) -join '、'
    Show-Toast "散户温度计：$day 更新失败" ("失败 $($summary.total - $summary.succeeded)/$($summary.total)：$detail。成功部分已保存，失败部分保留上次结果。点此查看日志。$warning") $log
} else {
    $reason = if ($summary.reason) { $summary.reason } else { $summary.status }
    Show-Toast '散户温度计：定时更新未运行' ("$reason。点此查看日志。$warning") $log
}
Write-Output "更新退出码 $exitCode；同步：$(if ($syncNote) { $syncNote } else { '正常' })"
Stop-Transcript | Out-Null
exit $exitCode
