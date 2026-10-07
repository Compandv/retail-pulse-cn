# Keep public/data in step with GitHub around the scheduled update.
# Only data commits are ever pushed; unpushed code commits stop the push.
$script:SyncRoot = Split-Path -Parent $PSScriptRoot
$script:SyncRetryWaitSeconds = 120

function Invoke-Git([string[]]$GitArgs) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'  # git writes progress to stderr
    try { $output = & git -C $script:SyncRoot @GitArgs 2>&1 | ForEach-Object { "$_" } }
    finally { $ErrorActionPreference = $previous }
    [pscustomobject]@{ Code = $LASTEXITCODE; Output = ($output -join "`n").Trim() }
}

function Get-SyncBranch { (Invoke-Git @('rev-parse', '--abbrev-ref', 'HEAD')).Output }

# Before collecting: fast-forward to GitHub so a cloud run's data is not collected twice.
# When an earlier unpushed data commit diverged from GitHub, replay it on top instead.
function Sync-DataPull($Python = $null) {
    if ((Get-SyncBranch) -ne 'main') { return '当前不在 main 分支，未从 GitHub 拉取' }
    if ((Invoke-Git @('fetch', '--quiet', 'origin', 'main')).Code -ne 0) { return '无法连接 GitHub，未拉取最新数据' }
    if ((Invoke-Git @('merge', '--ff-only', '--quiet', 'origin/main')).Code -eq 0) { return '' }
    $files = (Invoke-Git @('diff', '--name-only', 'origin/main...HEAD')).Output -split "`n" | Where-Object { $_ }
    if ($files | Where-Object { -not $_.StartsWith('public/data/') }) { return '本地有未推送的代码提交且与 GitHub 分叉，未自动拉取' }
    if (-not (Invoke-DataRebase $Python)) { return '本地与 GitHub 的数据冲突且无法自动解决，未拉取' }
    return ''
}

# Fetch with a few retries: a short network drop at 15:40 should not leave the day
# unpushed until the cloud fallback collects it a second time.
function Invoke-FetchWithRetry([int]$Attempts = 3) {
    for ($i = 1; $i -le $Attempts; $i++) {
        if ((Invoke-Git @('fetch', '--quiet', 'origin', 'main')).Code -eq 0) { return $true }
        if ($i -lt $Attempts) { Start-Sleep -Seconds $script:SyncRetryWaitSeconds }
    }
    return $false
}

# Replay unpushed data commits on GitHub's; data-only conflicts are settled file by file
# (scripts/resolve_data_conflict.py), anything else is aborted and left untouched.
function Invoke-DataRebase($Python) {
    # --autostash keeps uncommitted code edits aside; they never touch public/data.
    $rebase = Invoke-Git @('rebase', '--quiet', '--autostash', 'origin/main')
    for ($round = 0; $rebase.Code -ne 0 -and $round -lt 10; $round++) {
        if (-not $Python) { break }
        $previous = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try { & $Python.Path @($Python.Args) (Join-Path $PSScriptRoot 'resolve_data_conflict.py') $script:SyncRoot *> $null; $resolved = $LASTEXITCODE -eq 0 }
        finally { $ErrorActionPreference = $previous }
        if (-not $resolved) { break }
        $rebase = Invoke-Git @('-c', 'core.editor=true', 'rebase', '--continue')
    }
    if ($rebase.Code -ne 0) { [void](Invoke-Git @('rebase', '--abort')); return $false }
    return $true
}

# After collecting: commit public/data only, then push if every unpushed commit is data-only.
# Unpushed data commits from an earlier failed run are pushed by the next run.
function Sync-DataPush([string]$Day, $Python = $null) {
    if ((Get-SyncBranch) -ne 'main') { return '当前不在 main 分支，数据未同步到 GitHub' }
    $changed = (Invoke-Git @('status', '--porcelain', '--', 'public/data')).Output
    if ($changed) {
        [void](Invoke-Git @('add', '--', 'public/data'))
        $commit = Invoke-Git @('commit', '--quiet', '-m', "data: daily snapshot $Day (local)", '--', 'public/data')
        if ($commit.Code -ne 0) { return '数据提交失败，未推送' }
    }
    if (-not (Invoke-FetchWithRetry)) { return '无法连接 GitHub，数据已提交在本地，下次运行时自动补推' }
    $ahead = (Invoke-Git @('rev-list', 'origin/main..HEAD')).Output
    if (-not $ahead) { return '' }
    $files = (Invoke-Git @('diff', '--name-only', 'origin/main...HEAD')).Output -split "`n" | Where-Object { $_ }
    if ($files | Where-Object { -not $_.StartsWith('public/data/') }) { return '本地有未推送的代码提交，数据已提交但未推送' }
    $behind = (Invoke-Git @('rev-list', 'HEAD..origin/main')).Output
    if ($behind) {
        # GitHub moved on (for example the cloud fallback ran): replay the local data on top.
        if (-not (Invoke-DataRebase $Python)) { return '与 GitHub 上的数据冲突且无法自动解决，已提交到本地但未推送，需要手动处理' }
    }
    if ((Invoke-Git @('push', '--quiet', 'origin', 'main')).Code -eq 0) { return '' }
    return '推送到 GitHub 失败（可能是网络问题），下次运行时自动补推'
}
