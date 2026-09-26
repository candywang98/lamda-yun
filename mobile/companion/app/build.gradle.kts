import java.security.KeyFactory
import java.security.spec.X509EncodedKeySpec
import java.util.Base64

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

val configuredUpdatePublicKey = providers
    .gradleProperty("cloudctl.appUpdatePublicKey")
    .orElse(providers.environmentVariable("CLOUDCTL_APP_UPDATE_PUBLIC_KEY"))
val debugUpdatePublicKey =
    "MCowBQYDK2VwAyEA11qYAYKxCrfVS/7TyWQHOg7hcvPapiMlrwIaaPcHURo="
val sourceRevision = providers.exec {
    workingDir(rootDir.parentFile.parentFile)
    commandLine(
        "sh",
        "-c",
        "revision=\$(git describe --always 2>/dev/null) || revision=unknown; " +
            "if [ \"\$revision\" != unknown ] && " +
            "[ -n \"\$(git status --porcelain --untracked-files=normal -- . " +
            "':(exclude)mobile/companion/.gradle' 2>/dev/null)\" ]; then " +
            "printf '%s-dirty' \"\$revision\"; else printf '%s' \"\$revision\"; fi",
    )
}.standardOutput.asText.map { raw ->
    raw.trim().ifEmpty { "unknown" }.replace(Regex("[^A-Za-z0-9._-]"), "_")
}
val sourceRevisionLiteral = sourceRevision.map { "\"$it\"" }

android {
    namespace = "com.company.cloudctl.companion"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.company.cloudctl.companion"
        minSdk = 29
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        // Only the acceptance build type overrides this to true.
        buildConfigField("boolean", "IM_UPLOAD_HOLD_ALLOWED", "false")
        buildConfigField("boolean", "HEARTBEAT_DIAGNOSTIC", "false")
    }

    buildTypes {
        debug {
            // Side-by-side with a bound production install. Replacing
            // com.company.cloudctl.companion delivers MY_PACKAGE_REPLACED to
            // BootReceiver, which starts CompanionSyncService and claims.
            applicationIdSuffix = ".debug"
            // This public RFC 8032 vector is only for deterministic local unit tests.
            buildConfigField("String", "APP_UPDATE_PUBLIC_KEY", "\"$debugUpdatePublicKey\"")
            buildConfigField("String", "SOURCE_REVISION", sourceRevisionLiteral.get())
            buildConfigField(
                "String",
                "RECIPE_SIGNING_PUBLIC_KEYS",
                "\"{\\\"test-automation-1\\\":\\\"A6EHv/POEL4dcN0Y50vAmWfk1jCbpQ1fHdyGZBJVMbg=\\\",\\\"phase1-recipe-1\\\":\\\"LZxWUG0N3Ke3PiBS2nGPZm0PMVa2lIJfJQynfu/oR4M=\\\"}\"",
            )
        }
        release {
            isMinifyEnabled = true
            buildConfigField("String", "SOURCE_REVISION", sourceRevisionLiteral.get())
            buildConfigField(
                "String",
                "APP_UPDATE_PUBLIC_KEY",
                "\"${configuredUpdatePublicKey.getOrElse("")}\"",
            )
            buildConfigField("String", "RECIPE_SIGNING_PUBLIC_KEYS", "\"{}\"")
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
        // C6 install. Same upload path as release, plus the DUMP-protected
        // shell hold switch. Not the input-harness debug package or production.
        create("acceptance") {
            initWith(getByName("release"))
            applicationIdSuffix = ".acceptance"
            isDebuggable = false
            isMinifyEnabled = false
            matchingFallbacks += listOf("release")
            signingConfig = signingConfigs.getByName("debug")
            buildConfigField("boolean", "IM_UPLOAD_HOLD_ALLOWED", "true")
            buildConfigField("String", "APP_UPDATE_PUBLIC_KEY", "\"$debugUpdatePublicKey\"")
            buildConfigField("String", "SOURCE_REVISION", sourceRevisionLiteral.get())
            buildConfigField("String", "RECIPE_SIGNING_PUBLIC_KEYS", "\"{}\"")
        }
        // Explicitly authorized, in-place connectivity diagnosis only. Never a business runner.
        create("heartbeatDiagnostic") {
            initWith(getByName("release"))
            isDebuggable = true
            isMinifyEnabled = false
            matchingFallbacks += listOf("release")
            signingConfig = signingConfigs.getByName("debug")
            versionNameSuffix = "-connectivity-20260926"
            buildConfigField("boolean", "HEARTBEAT_DIAGNOSTIC", "true")
            buildConfigField("String", "APP_UPDATE_PUBLIC_KEY", "\"$debugUpdatePublicKey\"")
            buildConfigField("String", "RECIPE_SIGNING_PUBLIC_KEYS", "\"{}\"")
        }
    }

    sourceSets {
        getByName("acceptance") {
            java.srcDir("src/release/java")
        }
        getByName("heartbeatDiagnostic") {
            java.srcDir("src/release/java")
        }
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    testOptions {
        unitTests.isIncludeAndroidResources = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

android.sourceSets["test"].resources.srcDir("../../../contracts")

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2024.12.01")
    implementation(composeBom)
    androidTestImplementation(composeBom)

    implementation("androidx.activity:activity-compose:1.10.0")
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.7")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.7")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.10.1")
    implementation("org.bouncycastle:bcprov-jdk18on:1.85.2")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.jetbrains.kotlin:kotlin-test:2.1.0")
    testImplementation("org.json:json:20240303")
    testImplementation("androidx.test:core:1.6.1")
    testImplementation("org.robolectric:robolectric:4.14.1")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.test.espresso:espresso-core:3.6.1")
}

val verifyReleaseUpdatePublicKey by tasks.registering {
    group = "verification"
    description = "Requires a controlled Ed25519 update key before release packaging."
    doLast {
        val encoded = configuredUpdatePublicKey.orNull
            ?: throw GradleException(
                "Set CLOUDCTL_APP_UPDATE_PUBLIC_KEY or -Pcloudctl.appUpdatePublicKey for release.",
            )
        val decoded = try {
            Base64.getDecoder().decode(encoded)
        } catch (error: IllegalArgumentException) {
            throw GradleException("The release update public key must be valid Base64.", error)
        }
        if (decoded.size != 44) {
            throw GradleException("The release update public key must be a 44-byte X.509 Ed25519 key.")
        }
        try {
            KeyFactory.getInstance("Ed25519").generatePublic(X509EncodedKeySpec(decoded))
        } catch (error: Exception) {
            throw GradleException("The release update public key is not valid X.509 Ed25519.", error)
        }
        if (encoded == debugUpdatePublicKey) {
            throw GradleException("The public RFC 8032 test key cannot be used for release updates.")
        }
    }
}

afterEvaluate {
    tasks.named("preReleaseBuild").configure {
        dependsOn(verifyReleaseUpdatePublicKey)
    }
}
