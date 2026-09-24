plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.company.cloudctl.inputharness"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.company.cloudctl.inputharness"
        minSdk = 29
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildTypes {
        debug {
            // The only variant this module packages.
        }
    }
    // Remove the release variant before tasks are created. AGP always adds
    // one; deleting it here means assembleRelease / packageRelease are not
    // registered, so a release APK cannot be built from this module.
    androidComponents {
        beforeVariants(selector().withBuildType("release")) { variant ->
            variant.enable = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    testOptions {
        unitTests.isIncludeAndroidResources = true
    }
}

dependencies {
    testImplementation("junit:junit:4.13.2")
    testImplementation("androidx.test:core:1.6.1")
    testImplementation("org.robolectric:robolectric:4.14.1")
}

// A disabled release variant must not come back as a package task.
tasks.register("assertReleaseVariantAbsent") {
    group = "verification"
    description = "Fails if input-harness still has a release package task."
    doLast {
        val present = tasks.names.filter {
            it == "assembleRelease" || it == "packageRelease" || it == "bundleRelease"
        }
        if (present.isNotEmpty()) {
            throw GradleException("input-harness release tasks must be absent: $present")
        }
    }
}

tasks.register("assertNoReleaseArtifact") {
    group = "verification"
    description = "Fails if a release APK or bundle exists for the input harness."
    doLast {
        val outputs = layout.buildDirectory.get().asFile
        val forbidden = outputs.walkTopDown().filter { file ->
            file.isFile && (
                file.name.endsWith("-release.apk") ||
                    file.name.endsWith("-release.aab") ||
                    file.path.contains("/release/") && file.extension == "apk"
                )
        }.toList()
        if (forbidden.isNotEmpty()) {
            throw GradleException(
                "input-harness release artifact is forbidden: " + forbidden.joinToString { it.path },
            )
        }
    }
}

afterEvaluate {
    tasks.findByName("assembleDebug")?.finalizedBy("assertNoReleaseArtifact")
}
