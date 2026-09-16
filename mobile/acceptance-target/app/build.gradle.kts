plugins {
    id("com.android.application")
}

android {
    namespace = "com.company.cloudctl.testtarget"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.company.cloudctl.testtarget"
        minSdk = 29
        targetSdk = 35
        versionCode = 2
        versionName = "0.2.0"
    }
}
