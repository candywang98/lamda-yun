param(
    [Parameter(Mandatory = $true)][string] $Source,
    [Parameter(Mandatory = $true)][string] $Target,
    [Parameter(Mandatory = $true)][string] $OldPath,
    [Parameter(Mandatory = $true)][int] $StarterPid,
    [Parameter(Mandatory = $true)][int] $WrapperPid,
    [Parameter(Mandatory = $true)][string] $MarkerPath,
    [Parameter(Mandatory = $true)][string] $CleanupScript
)

$ErrorActionPreference = "Stop"

try {
    foreach ($processId in @($StarterPid, $WrapperPid)) {
        if ($processId -gt 0) {
            Wait-Process -Id $processId -ErrorAction SilentlyContinue
        }
    }
    Start-Sleep -Seconds 2

    $deadline = (Get-Date).AddMinutes(10)
    do {
        $users = @(Get-CimInstance Win32_Process | Where-Object {
            $_.ProcessId -ne $PID -and (
                $_.ExecutablePath -like "$Source*" -or $_.CommandLine -like "*$Source*"
            )
        })
        if ($users.Count -eq 0) {
            break
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)

    if ($users.Count -ne 0) {
        throw "Cache remains in use by $($users.Count) process(es)"
    }
    if (Test-Path -LiteralPath $OldPath) {
        throw "Old migration path already exists: $OldPath"
    }

    [IO.Directory]::Move($Source, $OldPath)
    New-Item -ItemType Junction -Path $Source -Target $Target | Out-Null

    $cleanupArguments = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $CleanupScript,
        "-OldPath", $OldPath,
        "-ParentPid", $PID,
        "-MarkerPath", $MarkerPath
    )
    Start-Process -FilePath "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" -ArgumentList $cleanupArguments -WindowStyle Hidden
} catch {
    "FAILED $(Get-Date -Format o) $($_.Exception.Message)" | Set-Content -LiteralPath $MarkerPath -Encoding UTF8
    exit 1
}
