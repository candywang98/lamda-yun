$ErrorActionPreference = "Stop"

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class NativeJunctionRemoval {
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool RemoveDirectory(string path);
}
"@

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

public static class NativePathMove {
    private const int MoveFileReplaceExisting = 0x1;
    private const int MoveFileDelayUntilReboot = 0x4;

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool MoveFileEx(string existingName, string newName, int flags);

    public static int Rename(string source, string destination) {
        return MoveFileEx(source, destination, MoveFileReplaceExisting) ? 0 : Marshal.GetLastWin32Error();
    }

    public static int DeleteOnReboot(string path) {
        return MoveFileEx(path, null, MoveFileDelayUntilReboot) ? 0 : Marshal.GetLastWin32Error();
    }
}
"@

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

public static class RawReparseRemoval {
    private const uint FileShareRead = 0x00000001;
    private const uint FileShareWrite = 0x00000002;
    private const uint FileShareDelete = 0x00000004;
    private const uint OpenExisting = 3;
    private const uint FileFlagOpenReparsePoint = 0x00200000;
    private const uint FileFlagBackupSemantics = 0x02000000;
    private const uint FsctlGetReparsePoint = 0x000900A8;
    private const uint FsctlDeleteReparsePoint = 0x000900AC;

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern SafeFileHandle CreateFile(
        string fileName,
        uint desiredAccess,
        uint shareMode,
        IntPtr securityAttributes,
        uint creationDisposition,
        uint flagsAndAttributes,
        IntPtr templateFile
    );

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool DeviceIoControl(
        SafeFileHandle device,
        uint controlCode,
        byte[] input,
        int inputLength,
        byte[] output,
        int outputLength,
        out int bytesReturned,
        IntPtr overlapped
    );

    public static int Delete(string path) {
        using (SafeFileHandle handle = CreateFile(
            path,
            0,
            FileShareRead | FileShareWrite | FileShareDelete,
            IntPtr.Zero,
            OpenExisting,
            FileFlagOpenReparsePoint | FileFlagBackupSemantics,
            IntPtr.Zero
        )) {
            if (handle.IsInvalid) {
                return Marshal.GetLastWin32Error();
            }

            byte[] reparseData = new byte[16384];
            int bytesReturned;
            if (!DeviceIoControl(
                handle,
                FsctlGetReparsePoint,
                null,
                0,
                reparseData,
                reparseData.Length,
                out bytesReturned,
                IntPtr.Zero
            )) {
                return Marshal.GetLastWin32Error();
            }

            byte[] deleteData = new byte[8];
            Array.Copy(reparseData, 0, deleteData, 0, 4);
            if (!DeviceIoControl(
                handle,
                FsctlDeleteReparsePoint,
                deleteData,
                deleteData.Length,
                null,
                0,
                out bytesReturned,
                IntPtr.Zero
            )) {
                return Marshal.GetLastWin32Error();
            }
            return 0;
        }
    }
}
"@

$junctions = [ordered]@{
    "C:\Users\Administrator\AppData\Local\pnpm" = "D:\android-tools\pnpm-local"
    "C:\Users\Administrator\AppData\Local\npm-cache" = "D:\android-tools\npm-cache"
    "C:\Users\Administrator\AppData\Roaming\npm" = "D:\android-tools\npm-global"
    "C:\Users\Administrator\AppData\Local\phone-control" = "D:\android-tools\phone-control"
    "C:\Users\Administrator\AppData\Local\Temp\node-compile-cache" = "D:\android-tools\tmp\node-compile-cache"
    "C:\Users\Administrator\AppData\Local\ms-playwright" = "D:\android-tools\playwright"
    "C:\Users\Administrator\AppData\Local\pip\Cache" = "D:\android-tools\user-cache\pip"
    "C:\Users\Administrator\AppData\Local\uv\cache" = "D:\android-tools\user-cache\uv"
}

foreach ($entry in $junctions.GetEnumerator()) {
    $source = [IO.Path]::GetFullPath($entry.Key).TrimEnd("\")
    $target = [IO.Path]::GetFullPath($entry.Value).TrimEnd("\")
    if (-not $source.StartsWith("C:\Users\Administrator\", [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing unexpected source path: $source"
    }
    if (-not $target.StartsWith("D:\", [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing unexpected target path: $target"
    }
    if (-not (Test-Path -LiteralPath $target -PathType Container)) {
        throw "Missing junction target: $target"
    }

    $sourceItem = Get-Item -LiteralPath $source -Force -ErrorAction SilentlyContinue
    if ($sourceItem) {
        if (($sourceItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) {
            throw "Refusing non-link source path: $source"
        }
        $extendedSource = "\\?\$source"
        $removed = [NativeJunctionRemoval]::RemoveDirectory($extendedSource)
        if (-not $removed) {
            $errorCode = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
            if ($errorCode -ne 649) {
                throw "Unable to remove broken junction ${source}: Win32 $errorCode"
            }
            $rawError = [RawReparseRemoval]::Delete($extendedSource)
            if ($rawError -ne 0) {
                $quarantine = "$source.invalid-reparse"
                if (Get-Item -LiteralPath $quarantine -Force -ErrorAction SilentlyContinue) {
                    throw "Quarantine path already exists: $quarantine"
                }
                $renameError = [NativePathMove]::Rename($extendedSource, "\\?\$quarantine")
                if ($renameError -ne 0) {
                    throw "Unable to quarantine invalid reparse data ${source}: Win32 $renameError"
                }
                $rebootError = [NativePathMove]::DeleteOnReboot("\\?\$quarantine")
                if ($rebootError -ne 0) {
                    Write-Warning "Could not schedule reboot cleanup for $quarantine (Win32 $rebootError)"
                }
                Write-Output "QUARANTINED $source -> $quarantine"
            } else {
                $children = @(Get-ChildItem -LiteralPath $source -Force)
                if ($children.Count -ne 0) {
                    throw "Refusing non-empty repaired directory: $source"
                }
                Remove-Item -LiteralPath $source -Force
            }
        }
    }

    $junction = New-Item -ItemType Junction -Path $source -Target $target
    if (($junction.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) {
        throw "Junction verification failed: $source"
    }
    Get-ChildItem -LiteralPath $source -Force -ErrorAction Stop | Select-Object -First 1 | Out-Null
    Write-Output "REPAIRED $source -> $target"
}
