plugins {
    id("com.android.application")
}

android {
    namespace = "cn.echoaiforever.phone_agent"
    compileSdk = 37

    defaultConfig {
        minSdk = 26
        targetSdk = 37
        versionCode = 1
        versionName = "0.1.0"
        buildConfigField("String", "DEFAULT_BASE_URL", "\"https://api.echoaiforever.cn\"")
    }

    flavorDimensions += "deployment"
    productFlavors {
        create("prod") {
            dimension = "deployment"
            applicationId = "cn.echoaiforever.phone_agent"
            resValue("string", "app_name", "Echo Phone Agent")
            buildConfigField(
                "String",
                "DEFAULT_BASE_URL",
                "\"https://api.echoaiforever.cn\"",
            )
        }
        create("local") {
            dimension = "deployment"
            applicationId = "cn.echoaiforever.phone_agent.local"
            resValue("string", "app_name", "Echo Phone Agent 本地")
            buildConfigField(
                "String",
                "DEFAULT_BASE_URL",
                "\"http://127.0.0.1:8000\"",
            )
        }
    }

    buildFeatures {
        buildConfig = true
        resValues = true
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
