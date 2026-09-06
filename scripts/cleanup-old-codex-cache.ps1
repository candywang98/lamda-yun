param(
    [Parameter(Mandatory = $true)][string] $OldPath,
    [Parameter(Mandatory = $true)][int] $ParentPid,
    [Parameter(Mandatory = $true)][string] $MarkerPath
)

$ErrorActionPreference = "Stop"
$expectedOldPath = "C:\Users\Administrator\.cache.c-migration-old"
$expectedLinkPath = "C:\Users\Administrator\.cache"
$expectedTargetPath = "D:\android-tools\user-cache"

try {
    if (-not [StringComparer]::OrdinalIgnoreCase.Equals(
        [IO.Path]::GetFullPath($OldPath).TrimEnd("\"),
        [IO.Path]::GetFullPath($expectedOldPath).TrimEnd("\")
    )) {
        throw "Refusing unexpected cleanup path: $OldPath"
    }

    if ($ParentPid -gt 0) {
        Wait-Process -Id $ParentPid -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 2

    $link = Get-Item -LiteralPath $expectedLinkPath -Force
    if (($link.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) {
        throw "Cache path is not a reparse point: $expectedLinkPath"
    }
    if (-not (Test-Path -LiteralPath $expectedTargetPath -PathType Container)) {
        throw "Cache target is missing: $expectedTargetPath"
    }

    $ownParentPid = (Get-CimInstance Win32_Process -Filter "ProcessId=$PID").ParentProcessId
    $deadline = (Get-Date).AddMinutes(10)
    do {
        $users = @(Get-CimInstance Win32_Process | Where-Object {
            $_.ProcessId -ne $PID -and $_.ProcessId -ne $ownParentPid -and (
                $_.ExecutablePath -like "$expectedOldPath*" -or $_.CommandLine -like "*$expectedOldPath*"
            )
        })
        if ($users.Count -eq 0) {
            break
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)

    if ($users.Count -ne 0) {
        throw "Old cache is still in use by $($users.Count) process(es)"
    }

    Get-ChildItem -LiteralPath $OldPath -Recurse -Force -ErrorAction SilentlyContinue | Where-Object {
        ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -and -not $_.PSIsContainer
    } | ForEach-Object {
        [IO.File]::Delete($_.FullName)
    }
    Remove-Item -LiteralPath $OldPath -Recurse -Force
    "OK $(Get-Date -Format o)" | Set-Content -LiteralPath $MarkerPath -Encoding ASCII
} catch {
    "FAILED $(Get-Date -Format o) $($_.Exception.Message)" | Set-Content -LiteralPath $MarkerPath -Encoding UTF8
    exit 1
}
