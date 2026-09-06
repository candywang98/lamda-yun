# Android build gate - 2026-08-31

This record covers the Companion and DPC Android projects after the machine owner accepted the Android
SDK licenses and Android 35 components were installed on D drive.

## Toolchain and artifacts

| Item | Evidence |
| --- | --- |
| JDK | Temurin OpenJDK `17.0.20.1`, `D:\android-tools\jdk-17.0.20.1+1` |
| Gradle | Project Wrapper `8.10.2` |
| Android Gradle Plugin | `8.7.3` |
| Android SDK | `D:\android-tools\sdk`; compile/target SDK 35; minimum SDK 29 |
| Companion APK | 54,377,889 bytes; SHA-256 `2346514784cce4f301b9e3f9613815efcfdca194da33b964347beb0d31873ff2` |
| DPC APK | 54,213,810 bytes; SHA-256 `90fb68621094a4f9a218b49fcf50d643f3d3a8ef5f02cb684128ecaefd806634` |

Both projects completed `assembleDebug`. APK Signature Scheme v2 debug-signature verification passed.
The Companion build included the source correction that removed the invalid internal Compose `weight`
import from `MainActivity.kt`.

## Authorized device smoke

Both APKs were installed with explicit `adb -s b0644fb5` targeting an LE2100 / OnePlus 9R running
Android 14 (SDK 34). Companion cold-started in approximately 1,201 ms and rendered its registration
screen. DPC cold-started in approximately 881 ms and rendered its policy screen. Crash and ANR scans
were clean. Evidence is stored under
`outputs/android-device/oneplus9r-20260831/android-build-install`.

DPC ownership remained deliberately unconfigured: `dpm list-owners` returned `no owners`. No device-owner,
work-profile, kiosk, managed-installation, or policy provisioning was attempted. The unrelated overlay
package `com.ydydyd8818` was not disabled.

## Remaining gates

This gate proves debug compilation, debug signing, installation, launch, and basic UI smoke on one
authorized physical device. It does not prove production release signing, upgrade/rollback, DPC
provisioning, real LAMDA connectivity, automation execution, compatibility promotion, soak/chaos, or
production rollout. Those remain task-specific external or hardware gates.
