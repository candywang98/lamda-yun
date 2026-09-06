# CloudCtl DPC

`com.company.cloudctl.dpc` is an optional, independently signed Android Enterprise device policy controller for company-owned, dedicated and resettable devices. It is not part of the ordinary Companion APK and refuses policy changes unless Android reports it as the device owner.

Build with JDK 17 and Android SDK 35:

```bash
./gradlew lint testDebugUnitTest assembleDebug
```

Provisioning and removal must follow the organization's Android Enterprise process. The app does not hide itself, block removal outside Android's standard owner rules, or enable arbitrary commands.

