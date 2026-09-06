# Verification status

- Toolchain found on 2026-08-31: Temurin JDK `17.0.20.1`, Gradle Wrapper `8.10.2`, and Android SDK
  at `D:\android-tools\sdk`. Only `build-tools;33.0.2` is installed and there is no SDK license
  directory.
- `scripts/run-android-gradle.ps1 -Project dpc -GradleArguments @('--offline','tasks')` completed
  successfully, proving Gradle/Kotlin DSL configuration without installing SDK packages.
- The Edge/Mobile contract suite passed 36 tests and the security boundary scan passed.
- `lint testDebugUnitTest assembleDebug` reached Android SDK resolution, then stopped because the
  machine owner has not accepted the licenses for `build-tools;34.0.0` and
  `platforms;android-35`. No APK was produced and this is not an APK build pass.
- Device-owner provisioning, kiosk allowlist, managed install behavior and Android 10-17 compatibility: `blocked_hardware` until a company-owned resettable test device is supplied.
- The DPC has a separate package, signing identity and audit boundary from Companion.
