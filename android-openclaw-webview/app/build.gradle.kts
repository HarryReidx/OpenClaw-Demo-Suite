plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

val defaultBaseUrl =
    (project.findProperty("OPENCLAW_BASE_URL") as String?)?.trim().orEmpty().ifBlank { "http://10.0.2.2:8105" }

android {
    namespace = "com.openclaw.mobile"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.openclaw.mobile"
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = "1.0.0"
        buildConfigField("String", "DEFAULT_BASE_URL", "\"$defaultBaseUrl\"")
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        buildConfig = true
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
    implementation("androidx.activity:activity-ktx:1.9.1")
    implementation("androidx.webkit:webkit:1.11.0")
}
