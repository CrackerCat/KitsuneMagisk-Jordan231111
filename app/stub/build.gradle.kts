plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.lsparanoid)
}

lsparanoid {
    seed = if (RAND_SEED != 0) RAND_SEED else null
    includeDependencies = true
    classFilter = { true }
}

android {
    namespace = "com.topjohnwu.magisk"
    enableKotlin = false

    defaultConfig {
        applicationId = APP_ID
        versionCode = 1
        versionName = "1.0"
        buildConfigField("int", "MANAGER_VERSION_CODE", "${Config.versionCode}")
        buildConfigField("int", "STUB_VERSION", Config.stubVersion)
    }

    buildTypes {
        release {
            proguardFiles("proguard-rules.pro")
            isMinifyEnabled = true
        }
    }

    buildFeatures {
        buildConfig = true
    }
}

setupStubApk()

dependencies {
    implementation(project(":shared"))
}
