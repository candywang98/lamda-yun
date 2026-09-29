# Android CI release update key

## Ownership and input

OWNER: the Android release owner controls the GitHub Actions repository variable
`CLOUDCTL_APP_UPDATE_PUBLIC_KEY`.

The value must be the Base64 encoding of a DER SubjectPublicKeyInfo (SPKI) Ed25519 **public** update
key. Never store a private key, seed, keystore, generated fallback, or RFC test vector in this
variable. Before initial configuration or rotation, review and record the decoded SPKI SHA-256
fingerprint, provenance, intended environment, and approving owner.

## CI boundary

The Android job maps only `${{ vars.CLOUDCTL_APP_UPDATE_PUBLIC_KEY }}` into the process environment.
An absent or empty repository variable stops the job before checkout; there is no fallback key. The
existing Companion Gradle verifier then rejects invalid Base64, a non-SPKI/non-Ed25519 value, and the
public RFC 8032 debug test key before the unchanged Companion and DPC `./gradlew lint test` suites.

Missing configuration therefore blocks Android release CI. Supplying the variable establishes the
required input boundary only; it does not by itself prove that Android CI, signing, packaging,
deployment, installation, or device acceptance passed.
