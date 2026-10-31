import java.io.File
import java.security.KeyStore
import java.security.MessageDigest
import java.security.PrivateKey
import java.security.cert.X509Certificate

plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

// Opt in explicitly. Ordinary development/release commands retain the established
// debug signer; no publisher identity is generated or silently substituted.
val productionSigningRequested = System.getenv("DRAGONHYDRA_ANDROID_PRODUCTION_SIGNING") == "1"
val productionSigningInputs: Map<String, String>? = if (productionSigningRequested) {
    require(!gradle.startParameter.isConfigurationCacheRequested) {
        "production_signing_configuration_invalid: disable configuration caching for publisher credentials."
    }
    val names = listOf("KEYSTORE", "KEY_ALIAS", "STORE_PASSWORD", "KEY_PASSWORD", "CERT_SHA256")
    val inputs = names.associateWith { name ->
        System.getenv("DRAGONHYDRA_ANDROID_$name")?.takeIf { it.isNotBlank() }
            ?: throw GradleException("requires_signing_configuration: missing protected publisher signing input.")
    }
    val suppliedKeyFile = File(inputs.getValue("KEYSTORE"))
    val keyFile = suppliedKeyFile.canonicalFile
    val expected = inputs.getValue("CERT_SHA256").replace(":", "").lowercase()
    val establishedDebug = "d77e623706f0146bc495904affe310cb492d67277ecf70b28455d1f5e138e419"
    require(suppliedKeyFile.isAbsolute && keyFile.isFile
        && expected.matches(Regex("[a-f0-9]{64}")) && expected != establishedDebug) {
        "production_signing_configuration_invalid: require an existing publisher key and its expected public certificate."
    }
    try {
        val store = KeyStore.getInstance(keyFile, inputs.getValue("STORE_PASSWORD").toCharArray())
        val alias = inputs.getValue("KEY_ALIAS")
        val key = store.getKey(alias, inputs.getValue("KEY_PASSWORD").toCharArray())
        val certificate = store.getCertificate(alias) as? X509Certificate
            ?: throw IllegalArgumentException()
        val actual = MessageDigest.getInstance("SHA-256").digest(certificate.encoded)
            .joinToString("") { byte -> "%02x".format(byte.toInt() and 0xff) }
        require(key is PrivateKey && actual == expected && actual != establishedDebug
            && !Regex("(?i)(?:^|,)\\s*CN\\s*=\\s*Android Debug(?:,|$)")
                .containsMatchIn(certificate.subjectX500Principal.name))
        certificate.checkValidity()
    } catch (_: Exception) {
        throw GradleException("production_signing_configuration_invalid: publisher key, passwords or certificate verification failed.")
    }
    inputs
} else null

android {
    namespace = "ai.dragonhydra.mobile"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        // Established update identity; retain when building development upgrades.
        applicationId = "ai.dragonhydra.mobile"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        // Uses the version code from pubspec.yaml. When using split APKs, 1000 * ABI_VERSION
        // is added automatically by Flutter. (https://developer.android.com/studio/build/configure-apk-splits#configure-APK-versions)
        // You can force using the value of versionCode by specifying the `-P force-version-code-ignoring-abi=true`
        // flag during build.
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    signingConfigs {
        if (productionSigningInputs != null) {
            create("production") {
                storeFile = File(productionSigningInputs.getValue("KEYSTORE"))
                storePassword = productionSigningInputs.getValue("STORE_PASSWORD")
                keyAlias = productionSigningInputs.getValue("KEY_ALIAS")
                keyPassword = productionSigningInputs.getValue("KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            // Development prereleases retain the existing Android Debug signer.
            // This is not a production publisher identity. The release script
            // verifies its fingerprint against the earlier published APK.
            signingConfig = signingConfigs.getByName(if (productionSigningRequested) "production" else "debug")
        }
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
