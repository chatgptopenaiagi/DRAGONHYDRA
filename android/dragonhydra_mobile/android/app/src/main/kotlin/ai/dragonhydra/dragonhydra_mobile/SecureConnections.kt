package ai.dragonhydra.mobile

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import io.flutter.plugin.common.BinaryMessenger
import io.flutter.plugin.common.MethodChannel
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** Encrypts provider keys with a non-exportable Android Keystore key. */
object SecureConnections {
    private const val alias = "dragonhydra.provider.credentials.v1"
    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(alias, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build())
        return generator.generateKey()
    }

    fun register(activity: Activity, messenger: BinaryMessenger) {
        MethodChannel(messenger, "ai.dragonhydra.mobile/connections").setMethodCallHandler { call, result ->
            try {
                if (call.method == "openUrl") {
                    val url = call.argument<String>("url") ?: ""
                    val uri = Uri.parse(url)
                    require(uri.scheme == "https" && !uri.host.isNullOrBlank() && uri.userInfo == null)
                    activity.startActivity(Intent(Intent.ACTION_VIEW, uri))
                    result.success(null)
                } else {
                    val id = call.argument<String>("providerId") ?: ""
                    require(id.matches(Regex("[a-z0-9_]{1,64}")))
                    val prefs = activity.getSharedPreferences("provider_vault_v1", Context.MODE_PRIVATE)
                    when (call.method) {
                        "save" -> {
                            val value = call.argument<String>("value") ?: ""
                            require(value.isNotBlank() && value.length <= 4096)
                            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
                            cipher.init(Cipher.ENCRYPT_MODE, key())
                            val encrypted = cipher.doFinal(value.toByteArray(Charsets.UTF_8))
                            val blob = cipher.iv + encrypted
                            check(prefs.edit().putString(id, Base64.encodeToString(blob, Base64.NO_WRAP)).commit())
                            result.success(null)
                        }
                        "read" -> {
                            val stored = prefs.getString(id, null)
                            if (stored == null) result.success(null) else {
                                val blob = Base64.decode(stored, Base64.NO_WRAP)
                                require(blob.size > 28)
                                val cipher = Cipher.getInstance("AES/GCM/NoPadding")
                                cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, blob.copyOfRange(0, 12)))
                                result.success(String(cipher.doFinal(blob.copyOfRange(12, blob.size)), Charsets.UTF_8))
                            }
                        }
                        "remove" -> {
                            check(prefs.edit().remove(id).commit())
                            result.success(null)
                        }
                        else -> result.notImplemented()
                    }
                }
            } catch (_: Exception) {
                // Never surface values, platform exception text, or encrypted blobs to logs.
                result.error("CONNECTION_OPERATION_FAILED", "Secure connection operation failed.", null)
            }
        }
    }
}
