# P4-001 evidence summary

- Task: Kotlin Companion 入网与设备绑定
- Audited: 2026-08-31
- Software status: `implemented`
- Acceptance status: `blocked_hardware`

## Proven evidence

- Implementation/configuration: `mobile/companion/app/src/main/java/com/company/cloudctl/companion/data/CompanionRepository.kt`
- Implementation/configuration: `mobile/companion/app/src/main/java/com/company/cloudctl/companion/network/EnrollmentParser.kt`
- Implementation/configuration: `mobile/companion/app/src/main/java/com/company/cloudctl/companion/network/EdgeClient.kt`
- Software test evidence: `tests/mobile_project_test.py`
- Software test evidence: `mobile/companion/app/src/test/java/com/company/cloudctl/companion/network/EnrollmentParserTest.kt`
- Local process evidence is explicitly classified `mock_only` with `hardwareEvidence=false`.

## Hardware boundary

No authorized Android/LAMDA device evidence, signed APK installation evidence, or production device result is present. Mock, simulator, and source-structure tests are not hardware acceptance.

