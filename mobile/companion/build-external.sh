#!/bin/sh
set -eu

ROOT="$HOME/CloudCtlExternal"
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export JAVA_HOME="$ROOT/jdks/temurin-17/Contents/Home"
export ANDROID_HOME="$ROOT/android-sdk"
export ANDROID_SDK_ROOT="$ROOT/android-sdk"
export ANDROID_USER_HOME="$ROOT/android-user-home"
export GRADLE_USER_HOME="$ROOT/gradle-home"

# Gradle reads JVM proxy settings rather than the shell's https_proxy variable.
export GRADLE_OPTS="${GRADLE_OPTS:-} -Dhttp.proxyHost=127.0.0.1 -Dhttp.proxyPort=7897 -Dhttps.proxyHost=127.0.0.1 -Dhttps.proxyPort=7897"

cd "$SCRIPT_DIR"
exec ./gradlew --project-cache-dir "$ROOT/project-cache/companion" "$@"
