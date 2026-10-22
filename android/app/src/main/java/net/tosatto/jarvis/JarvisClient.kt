package net.tosatto.jarvis

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

data class Session(val access: String, val refresh: String)
data class Household(val id: String, val name: String, val role: String)
data class JarvisTask(
    val id: String,
    val title: String,
    val notes: String,
    val priority: String,
    val dueAt: String?,
    val personId: String?,
    val documentId: String?,
)

class SecureSessionStore(context: Context) {
    private val preferences = context.getSharedPreferences("secure_session", Context.MODE_PRIVATE)
    private val alias = "jarvis-session-key"

    fun load(): Session? = runCatching {
        val packed = Base64.decode(preferences.getString("value", null), Base64.NO_WRAP)
        val iv = packed.copyOfRange(0, 12)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, iv))
        val json = JSONObject(String(cipher.doFinal(packed.copyOfRange(12, packed.size))))
        Session(json.getString("access"), json.getString("refresh"))
    }.getOrNull()

    fun save(session: Session) {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key())
        val plain = JSONObject().put("access", session.access).put("refresh", session.refresh)
        val packed = cipher.iv + cipher.doFinal(plain.toString().toByteArray())
        preferences.edit().putString("value", Base64.encodeToString(packed, Base64.NO_WRAP)).apply()
    }

    fun clear() = preferences.edit().clear().apply()

    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(alias, null) as? SecretKey)?.let { return it }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").run {
            init(
                KeyGenParameterSpec.Builder(
                    alias,
                    KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
                ).setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                    .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                    .build(),
            )
            generateKey()
        }
    }
}

class JarvisClient(private val store: SecureSessionStore) {
    suspend fun login(email: String, password: String): Session = withContext(Dispatchers.IO) {
        val result = request(
            "POST",
            "/api/v1/auth/login",
            JSONObject().put("email", email).put("password", password).toString().toByteArray(),
            "application/json",
            false,
        )
        Session(result.getString("access_token"), result.getString("refresh_token")).also(store::save)
    }

    suspend fun households(): List<Household> = withContext(Dispatchers.IO) {
        val values = requestArray("GET", "/api/v1/households")
        (0 until values.length()).map { index ->
            values.getJSONObject(index).run { Household(getString("id"), getString("name"), getString("role")) }
        }
    }

    suspend fun tasks(householdId: String): List<JarvisTask> = withContext(Dispatchers.IO) {
        val values = requestArray("GET", "/api/v1/households/$householdId/tasks")
        (0 until values.length()).map { index ->
            values.getJSONObject(index).run {
                JarvisTask(
                    getString("id"),
                    getString("title"),
                    getString("notes"),
                    getString("priority"),
                    nullableString("due_at"),
                    nullableString("person_id"),
                    nullableString("document_id"),
                )
            }
        }
    }

    suspend fun complete(householdId: String, task: JarvisTask) = withContext(Dispatchers.IO) {
        val body = JSONObject().put("title", task.title).put("notes", task.notes)
            .put("priority", task.priority).put("status", "done")
            .put("due_at", task.dueAt).put("person_id", task.personId)
            .put("document_id", task.documentId)
        request("PUT", "/api/v1/households/$householdId/tasks/${task.id}", body.toString().toByteArray(), "application/json")
    }

    suspend fun createTask(householdId: String, title: String) = withContext(Dispatchers.IO) {
        val body = JSONObject().put("title", title.trim())
        request(
            "POST",
            "/api/v1/households/$householdId/tasks",
            body.toString().toByteArray(),
            "application/json",
        )
    }

    suspend fun upload(householdId: String, filename: String, mediaType: String, content: ByteArray) = withContext(Dispatchers.IO) {
        request("POST", "/api/v1/households/$householdId/documents", content, mediaType, headers = mapOf("X-Filename" to filename))
    }

    private fun requestArray(method: String, path: String) = JSONArray(requestText(method, path))

    private fun request(method: String, path: String, body: ByteArray? = null, contentType: String? = null, authenticated: Boolean = true, headers: Map<String, String> = emptyMap()): JSONObject = JSONObject(requestText(method, path, body, contentType, authenticated, headers))

    private fun requestText(method: String, path: String, body: ByteArray? = null, contentType: String? = null, authenticated: Boolean = true, headers: Map<String, String> = emptyMap(), retry: Boolean = true): String {
        val connection = URL(BuildConfig.API_BASE_URL.trimEnd('/') + path).openConnection() as HttpURLConnection
        connection.requestMethod = method
        connection.connectTimeout = 10_000
        connection.readTimeout = 30_000
        connection.setRequestProperty("Accept", "application/json")
        if (authenticated) connection.setRequestProperty("Authorization", "Bearer ${store.load()?.access ?: error("Sessione assente")}")
        if (contentType != null) connection.setRequestProperty("Content-Type", contentType)
        headers.forEach(connection::setRequestProperty)
        if (body != null) connection.outputStream.use { it.write(body) }
        val status = connection.responseCode
        val text = (if (status in 200..299) connection.inputStream else connection.errorStream)?.bufferedReader()?.use { it.readText() }.orEmpty()
        if (status == 401 && authenticated && retry) {
            refreshSession()
            return requestText(method, path, body, contentType, true, headers, false)
        }
        if (status !in 200..299) error("Richiesta non riuscita (HTTP $status)")
        return text.ifBlank { "{}" }
    }

    private fun refreshSession() {
        val current = store.load() ?: error("Sessione scaduta")
        val body = JSONObject().put("refresh_token", current.refresh).toString().toByteArray()
        val result = JSONObject(requestText("POST", "/api/v1/auth/refresh", body, "application/json", false))
        store.save(Session(result.getString("access_token"), result.getString("refresh_token")))
    }

    private fun JSONObject.nullableString(name: String): String? =
        if (isNull(name)) null else getString(name).ifBlank { null }
}
