$ErrorActionPreference = "Stop"

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class NativeDirectoryRemoval {
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool RemoveDirectory(string path);
}
"@

$allowedSources = @(
    "C:\Users\Administrator\AppData\Local\pnpm",
    "C:\Users\Administrator\AppData\Local\npm-cache",
    "C:\Users\Administrator\AppData\Roaming\npm",
    "C:\Users\Administrator\AppData\Local\phone-control",
    "C:\Users\Administrator\Documents\Codex\2026-08-30\apk\.tmp",
    "C:\Users\Administrator\Documents\Codex\2026-08-30\apk\work",
    "C:\Users\Administrator\AppData\Local\Temp\node-compile-cache",
    "C:\Users\Administrator\AppData\Local\ms-playwright",
    "C:\Users\Administrator\AppData\Local\pip\Cache",
    "C:\Users\Administrator\AppData\Local\uv\cache",
    "C:\Users\Administrator\.android"
)

function Assert-AllowedSource {
    param([Parameter(Mandatory = $true)][string] $Path)

    $resolved = [IO.Path]::GetFullPath($Path).TrimEnd("\")
    $allowed = $allowedSources | Where-Object {
        [StringComparer]::OrdinalIgnoreCase.Equals(
            [IO.Path]::GetFullPath($_).TrimEnd("\"),
            $resolved
        )
    }
    if (-not $allowed) {
        throw "Refusing unapproved source path: $resolved"
    }
}

function Get-TreeStats {
    param([Parameter(Mandatory = $true)][string] $Path)

    $files = @(Get-ChildItem -LiteralPath $Path -File -Recurse -Force)
    return [pscustomobject]@{
        Count = $files.Count
        Bytes = ($files | Measure-Object Length -Sum).Sum
    }
}

function Move-DirectoryToJunction {
    param(
        [Parameter(Mandatory = $true)][string] $Source,
        [Parameter(Mandatory = $true)][string] $Target
    )

    Assert-AllowedSource -Path $Source
    if (-not (Test-Path -LiteralPath $Source)) {
        New-Item -ItemType Directory -Path $Target -Force | Out-Null
        New-Item -ItemType Junction -Path $Source -Target $Target | Out-Null
        Write-Output "LINKED missing source: $Source -> $Target"
        return
    }

    $sourceItem = Get-Item -LiteralPath $Source -Force
    if (($sourceItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        Write-Output "SKIPPED existing link: $Source -> $($sourceItem.Target -join ';')"
        return
    }

    $nestedLinks = @(Get-ChildItem -LiteralPath $Source -Recurse -Force | Where-Object {
        ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0
    })

    New-Item -ItemType Directory -Path $Target -Force | Out-Null
    & "C:\Windows\System32\Robocopy.exe" $Source $Target /E /COPY:DAT /DCOPY:DAT /R:2 /W:1 /SJ /SL /NFL /NDL /NJH /NJS /NP
    if ($LASTEXITCODE -ge 8) {
        throw "robocopy failed: $Source -> $Target (exit $LASTEXITCODE)"
    }

    $sourceStats = Get-TreeStats -Path $Source
    $missing = 0
    Get-ChildItem -LiteralPath $Source -File -Recurse -Force | ForEach-Object {
        $relativePath = $_.FullName.Substring($Source.TrimEnd("\").Length).TrimStart("\")
        $destination = Join-Path $Target $relativePath
        if (-not (Test-Path -LiteralPath $destination -PathType Leaf)) {
            $missing += 1
        } elseif ((Get-Item -LiteralPath $destination -Force).Length -ne $_.Length) {
            $missing += 1
        }
    }
    if ($missing -ne 0) {
        throw "Verification failed for ${Source}: $missing missing or mismatched files"
    }

    $targetStats = Get-TreeStats -Path $Target
    if ($targetStats.Count -lt $sourceStats.Count -or $targetStats.Bytes -lt $sourceStats.Bytes) {
        throw "Target is smaller than source: $Target"
    }

    $checkedItem = Get-Item -LiteralPath $Source -Force
    if (($checkedItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Refusing recursive deletion of a reparse point: $Source"
    }

    $nestedLinks | Sort-Object { $_.FullName.Length } -Descending | ForEach-Object {
        if (($_.Attributes -band [IO.FileAttributes]::Directory) -ne 0) {
            $removed = [NativeDirectoryRemoval]::RemoveDirectory($_.FullName)
            if (-not $removed) {
                $errorCode = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
                if ($errorCode -ne 2 -and $errorCode -ne 3) {
                    throw "Unable to remove nested directory link $($_.FullName): Win32 $errorCode"
                }
            }
        } else {
            [IO.File]::Delete($_.FullName)
        }
    }
    Remove-Item -LiteralPath $Source -Recurse -Force
    New-Item -ItemType Junction -Path $Source -Target $Target | Out-Null
    Write-Output ("MIGRATED {0}: {1} files, {2:N1} MB -> {3}" -f $Source, $sourceStats.Count, ($sourceStats.Bytes / 1MB), $Target)
}

$cloudLink = "C:\Users\Administrator\Documents\Codex\2026-08-30\apk\work\cloudctl"
if (Test-Path -LiteralPath $cloudLink) {
    $cloudLinkItem = Get-Item -LiteralPath $cloudLink -Force
    if (($cloudLinkItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        [IO.Directory]::Delete($cloudLink)
    }
}

Move-DirectoryToJunction "C:\Users\Administrator\AppData\Local\pnpm" "D:\android-tools\pnpm-local"
Move-DirectoryToJunction "C:\Users\Administrator\AppData\Local\npm-cache" "D:\android-tools\npm-cache"
Move-DirectoryToJunction "C:\Users\Administrator\AppData\Roaming\npm" "D:\android-tools\npm-global"
Move-DirectoryToJunction "C:\Users\Administrator\AppData\Local\phone-control" "D:\android-tools\phone-control"
Move-DirectoryToJunction "C:\Users\Administrator\Documents\Codex\2026-08-30\apk\.tmp" "D:\Codex\2026-08-30\apk\.tmp"
Move-DirectoryToJunction "C:\Users\Administrator\Documents\Codex\2026-08-30\apk\work" "D:\Codex\2026-08-30\apk\work"
Move-DirectoryToJunction "C:\Users\Administrator\AppData\Local\Temp\node-compile-cache" "D:\android-tools\tmp\node-compile-cache"
Move-DirectoryToJunction "C:\Users\Administrator\AppData\Local\ms-playwright" "D:\android-tools\playwright"
Move-DirectoryToJunction "C:\Users\Administrator\AppData\Local\pip\Cache" "D:\android-tools\user-cache\pip"
Move-DirectoryToJunction "C:\Users\Administrator\AppData\Local\uv\cache" "D:\android-tools\user-cache\uv"
Move-DirectoryToJunction "C:\Users\Administrator\.android" "D:\android-tools\android-user"

$legacyTarget = "D:\android-tools\legacy-temp"
New-Item -ItemType Directory -Path $legacyTarget -Force | Out-Null
$legacyNames = @(
    "hongyu-local-build",
    "hongyu-local-v7.8.2.apk",
    "hongyu-local-final.apk",
    "hongyu-local-clone.apk"
)
$legacyItems = @(
    Get-ChildItem -LiteralPath "C:\Users\Administrator\AppData\Local\Temp" -Force | Where-Object {
        $_.Name -in $legacyNames -or $_.Name -like "aapt2_*.tmp"
    }
)
foreach ($item in $legacyItems) {
    $destination = Join-Path $legacyTarget $item.Name
    if ($item.PSIsContainer) {
        if ($item.Name -ne "hongyu-local-build") {
            throw "Unexpected legacy directory: $($item.FullName)"
        }
        $allowedSources += $item.FullName
        Move-DirectoryToJunction $item.FullName $destination
    } else {
        Copy-Item -LiteralPath $item.FullName -Destination $destination -Force
        if ((Get-Item -LiteralPath $destination).Length -ne $item.Length) {
            throw "File verification failed: $($item.FullName)"
        }
        Remove-Item -LiteralPath $item.FullName -Force
        Write-Output "MIGRATED FILE: $($item.FullName) -> $destination"
    }
}
