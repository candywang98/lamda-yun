# Verification status

- Toolchain found on 2026-08-31: Temurin JDK `17.0.20.1`, Gradle Wrapper `8.10.2`, and Android SDK
  at `D:\android-tools\sdk`. Only `build-tools;33.0.2` is installed and there is no SDK license
  directory.
- `scripts/run-android-gradle.ps1 -Project companion -GradleArguments @('--offline','tasks')`
  completed successfully, proving Gradle/Kotlin DSL configuration without installing SDK packages.
- The release update key gate passed with a different valid X.509 Ed25519 public key and rejected
  both a missing key and the public RFC 8032 debug test key.
- The Edge/Mobile contract suite passed 36 tests and the complete local runtime acceptance passed in
  `mock_only` mode.
- `lint testDebugUnitTest assembleDebug` reached Android SDK resolution, then stopped because the
  machine owner has not accepted the licenses for `build-tools;34.0.0` and
  `platforms;android-35`. No APK was produced and this is not an APK build pass.
- `connectedCheck`, enrollment against an authorized Edge, permission prompts, emergency stop, update signature UI and Android 10-17 compatibility: `blocked_hardware` until an authorized device and Edge test identity are supplied.
- Mock or emulator results do not satisfy the real-device acceptance gate.
