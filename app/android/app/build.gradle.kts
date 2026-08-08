import java.util.Properties

plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

val localProperties = Properties()
val localPropertiesFile = rootProject.file("local.properties")
if (localPropertiesFile.exists()) {
    localPropertiesFile.inputStream().use(localProperties::load)
}
val getuiAppId =
    providers.gradleProperty("echo.getuiAppId").orNull
        ?: localProperties.getProperty("echo.getuiAppId")
        ?: System.getenv("ECHO_GETUI_APP_ID")
        ?: ""
require(getuiAppId.isNotBlank()) {
    "Getui AppID is required. Set echo.getuiAppId in android/local.properties or ECHO_GETUI_APP_ID."
}

val keystorePropertiesFile = rootProject.file("key.properties")
val keystoreProperties = Properties()
val releaseSigningConfigured = keystorePropertiesFile.exists()
if (releaseSigningConfigured) {
    keystorePropertiesFile.inputStream().use(keystoreProperties::load)
}

android {
    namespace = "cn.echoaiforever.echo_app"
    compileSdk = 37
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        applicationId = "cn.echoaiforever.echo_app"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
        manifestPlaceholders["GETUI_APPID"] = getuiAppId
    }

    signingConfigs {
        if (releaseSigningConfigured) {
            create("release") {
                keyAlias = keystoreProperties.getProperty("keyAlias")
                keyPassword = keystoreProperties.getProperty("keyPassword")
                storeFile = file(keystoreProperties.getProperty("storeFile"))
                storePassword = keystoreProperties.getProperty("storePassword")
            }
        }
    }

    buildTypes {
        release {
            signingConfig = signingConfigs.findByName("release")
        }
    }
}

gradle.taskGraph.whenReady {
    val buildsRelease = allTasks.any { task ->
        task.name.contains("Release", ignoreCase = true)
    }
    if (buildsRelease && !releaseSigningConfigured) {
        throw GradleException(
            "Release signing is not configured. Create android/key.properties before building.",
        )
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}

dependencies {
    implementation("com.getui:gtsdk:3.3.12.0")
    implementation("com.getui:gtc:3.2.18.0")
}
