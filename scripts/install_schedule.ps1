# Register (or remove with -Uninstall) the weekday scheduled update for the current user.
param([string]$Time = '15:40', [switch]$FailuresOnly, [switch]$Uninstall)
$ErrorActionPreference = 'Stop'
$taskName = 'RetailPulse-DailyUpdate'

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "已删除计划任务 $taskName。"
    } else {
        Write-Host "计划任务 $taskName 不存在。"
    }
    exit 0
}

if ($Time -notmatch '^\d{1,2}:\d{2}$') { Write-Error '时间格式应为 HH:mm，例如 15:40。'; exit 1 }
$script = Join-Path $PSScriptRoot 'scheduled_update.ps1'
$arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`""
if ($FailuresOnly) { $arguments += ' -FailuresOnly' }
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arguments -WorkingDirectory (Split-Path -Parent $PSScriptRoot)
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday -At $Time
# StartWhenAvailable: a run missed while the PC was off happens at next logon;
# update_index --if-stale then collects the missed session or exits quickly.
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew
# Interactive + Limited: runs as you, only while logged on, without admin rights, so toasts are visible.
$principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
    -Description '散户温度计：工作日收盘后更新过期快照，并以系统通知报告结果。' -Force | Out-Null
Write-Host "已注册计划任务 $taskName：每周一至周五 $Time 运行（错过时开机后补跑）。"
Write-Host "立即试运行：Start-ScheduledTask -TaskName $taskName；删除：scripts\install_schedule.ps1 -Uninstall"
