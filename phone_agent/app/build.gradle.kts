plugins {
    id("com.android.application")
}

android {
    namespace = "cn.echoaiforever.phone_agent"
    compileSdk = 37

    defaultConfig {
        applicationId = "cn.echoaiforever.phone_agent"
        minSdk = 26
        targetSdk = 37
        versionCode = 1
        versionName = "0.1.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

dependencies {
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
}
