# Keep public/data in step with GitHub around the scheduled update.
# Only data commits are ever pushed; unpushed code commits stop the push.
$script:SyncRoot = Split-Path -Parent $PSScriptRoot

function Invoke-Git([string[]]$GitArgs) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'  # git writes progress to stderr
    try { $output = & git -C $script:SyncRoot @GitArgs 2>&1 | ForEach-Object { "$_" } }
    finally { $ErrorActionPreference = $previous }
    [pscustomobject]@{ Code = $LASTEXITCODE; Output = ($output -join "`n").Trim() }
}

function Get-SyncBranch { (Invoke-Git @('rev-parse', '--abbrev-ref', 'HEAD')).Output }

# Before collecting: fast-forward to GitHub so a cloud run's data is not collected twice.
function Sync-DataPull {
    if ((Get-SyncBranch) -ne 'main') { return '当前不在 main 分支，未从 GitHub 拉取' }
    if ((Invoke-Git @('fetch', '--quiet', 'origin', 'main')).Code -ne 0) { return '无法连接 GitHub，未拉取最新数据' }
    $merge = Invoke-Git @('merge', '--ff-only', '--quiet', 'origin/main')
    if ($merge.Code -ne 0) { return '本地与 GitHub 有分叉，未自动拉取' }
    return ''
}

# After collecting: commit public/data only, then push if every unpushed commit is data-only.
function Sync-DataPush([string]$Day) {
    if ((Get-SyncBranch) -ne 'main') { return '当前不在 main 分支，数据未同步到 GitHub' }
    $changed = (Invoke-Git @('status', '--porcelain', '--', 'public/data')).Output
    if ($changed) {
        [void](Invoke-Git @('add', '--', 'public/data'))
        $commit = Invoke-Git @('commit', '--quiet', '-m', "data: daily snapshot $Day (local)", '--', 'public/data')
        if ($commit.Code -ne 0) { return '数据提交失败，未推送' }
    }
    [void](Invoke-Git @('fetch', '--quiet', 'origin', 'main'))
    $ahead = (Invoke-Git @('rev-list', 'origin/main..HEAD')).Output
    if (-not $ahead) { return '' }
    $files = (Invoke-Git @('diff', '--name-only', 'origin/main..HEAD')).Output -split "`n" | Where-Object { $_ }
    if ($files | Where-Object { -not $_.StartsWith('public/data/') }) { return '本地有未推送的代码提交，数据已提交但未推送' }
    if ((Invoke-Git @('push', '--quiet', 'origin', 'main')).Code -eq 0) { return '' }
    # GitHub moved on (for example a cloud run): replay the data commit on top once.
    $rebase = Invoke-Git @('pull', '--rebase', '--autostash', '--quiet', 'origin', 'main')
    if ($rebase.Code -ne 0) {
        [void](Invoke-Git @('rebase', '--abort'))
        return '与 GitHub 上的数据冲突，已提交到本地但未推送，需要手动处理'
    }
    if ((Invoke-Git @('push', '--quiet', 'origin', 'main')).Code -ne 0) { return '推送到 GitHub 失败，下次运行时会重试' }
    return ''
}
