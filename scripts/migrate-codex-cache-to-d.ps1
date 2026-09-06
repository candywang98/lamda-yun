$ErrorActionPreference = "Stop"

$source = "C:\Users\Administrator\.cache"
$target = "D:\android-tools\user-cache"
$oldPath = "C:\Users\Administrator\.cache.c-migration-old"
$markerPath = "D:\android-tools\cache-migration-status.txt"
$cleanupScript = "D:\Codex\2026-08-30\apk\work\cloudctl\scripts\cleanup-old-codex-cache.ps1"
$switchScript = "D:\Codex\2026-08-30\apk\work\cloudctl\scripts\perform-deferred-cache-switch.ps1"

if (-not [StringComparer]::OrdinalIgnoreCase.Equals(
    [IO.Path]::GetFullPath($source).TrimEnd("\"),
    "C:\Users\Administrator\.cache"
)) {
    throw "Unexpected source path: $source"
}
if (Test-Path -LiteralPath $oldPath) {
    throw "Previous migration directory already exists: $oldPath"
}

$sourceItem = Get-Item -LiteralPath $source -Force
if (($sourceItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
    Write-Output "SKIPPED existing cache link: $source -> $($sourceItem.Target -join ';')"
    exit 0
}

New-Item -ItemType Directory -Path $target -Force | Out-Null
& "C:\Windows\System32\Robocopy.exe" $source $target /E /COPY:DAT /DCOPY:DAT /R:2 /W:1 /SJ /SL /NFL /NDL /NJH /NJS /NP
if ($LASTEXITCODE -ge 8) {
    throw "robocopy failed: $source -> $target (exit $LASTEXITCODE)"
}

$sourceFiles = @(Get-ChildItem -LiteralPath $source -File -Recurse -Force)
$sourceBytes = ($sourceFiles | Measure-Object Length -Sum).Sum
$missing = 0
foreach ($file in $sourceFiles) {
    $relativePath = $file.FullName.Substring($source.TrimEnd("\").Length).TrimStart("\")
    $destination = Join-Path $target $relativePath
    if (-not (Test-Path -LiteralPath $destination -PathType Leaf)) {
        $missing += 1
    } elseif ((Get-Item -LiteralPath $destination -Force).Length -ne $file.Length) {
        $missing += 1
    }
}
if ($missing -ne 0) {
    throw "Cache verification failed: $missing missing or mismatched files"
}

Remove-Item -LiteralPath $markerPath -Force -ErrorAction SilentlyContinue
$wrapperPid = (Get-CimInstance Win32_Process -Filter "ProcessId=$PID").ParentProcessId
$arguments = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", $switchScript,
    "-Source", $source,
    "-Target", $target,
    "-OldPath", $oldPath,
    "-StarterPid", $PID,
    "-WrapperPid", $wrapperPid,
    "-MarkerPath", $markerPath,
    "-CleanupScript", $cleanupScript
)
Start-Process -FilePath "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" -ArgumentList $arguments -WindowStyle Hidden

Write-Output ("COPIED CACHE: {0} files, {1:N1} MB -> {2}" -f $sourceFiles.Count, ($sourceBytes / 1MB), $target)
Write-Output "Deferred switch scheduled: $source -> $target"
