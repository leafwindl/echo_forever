package cn.echoaiforever.echo_app

import android.app.DownloadManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInfo
import android.content.pm.PackageInstaller
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.provider.Settings
import android.util.Log
import android.widget.Toast
import io.flutter.plugin.common.BinaryMessenger
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import org.json.JSONObject
import java.io.File
import java.io.FileInputStream
import java.security.MessageDigest
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.Future

class DirectUpdatePlugin(private val activity: MainActivity) : MethodChannel.MethodCallHandler {
    companion object {
        private const val CHANNEL_NAME = "cn.echoaiforever.echo_app/direct_update"
        private const val APK_MIME_TYPE = "application/vnd.android.package-archive"
        private const val PREFERENCES_NAME = "echo_direct_updates"
        private const val META_PREFIX = "download_"
        private const val INSTALL_RESULT_ACTION =
            "cn.echoaiforever.echo_app.UPDATE_INSTALL_RESULT"
        private const val LOG_TAG = "EchoDirectUpdate"
    }

    private val downloadManager =
        activity.getSystemService(Context.DOWNLOAD_SERVICE) as DownloadManager
    private val preferences =
        activity.getSharedPreferences(PREFERENCES_NAME, Context.MODE_PRIVATE)
    private val executor: ExecutorService = Executors.newSingleThreadExecutor()
    private val verificationTasks = ConcurrentHashMap<Long, Future<Unit>>()
    private lateinit var channel: MethodChannel

    fun register(messenger: BinaryMessenger) {
        channel = MethodChannel(messenger, CHANNEL_NAME)
        channel.setMethodCallHandler(this)
    }

    fun dispose() {
        if (::channel.isInitialized) {
            channel.setMethodCallHandler(null)
        }
        executor.shutdownNow()
    }

    fun handleInstallResult(intent: Intent?) {
        if (intent?.action != INSTALL_RESULT_ACTION) return
        intent.action = null
        val status = intent.getIntExtra(
            PackageInstaller.EXTRA_STATUS,
            PackageInstaller.STATUS_FAILURE,
        )
        val message = intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE).orEmpty()
        when (status) {
            PackageInstaller.STATUS_PENDING_USER_ACTION -> {
                val confirmation = installConfirmationIntent(intent)
                if (confirmation == null) {
                    Log.e(LOG_TAG, "Installer confirmation intent is missing")
                    showInstallFailure("系统没有返回安装确认页面")
                    return
                }
                try {
                    activity.startActivity(confirmation)
                } catch (error: Exception) {
                    Log.e(LOG_TAG, "Unable to launch installer confirmation", error)
                    showInstallFailure(error.message ?: "无法打开系统安装确认页面")
                }
            }
            PackageInstaller.STATUS_SUCCESS -> {
                Log.i(LOG_TAG, "Package update installed successfully")
            }
            else -> {
                Log.e(LOG_TAG, "Package installation failed: status=$status message=$message")
                showInstallFailure(message.ifBlank { "系统安装失败（状态码 $status）" })
            }
        }
    }

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        try {
            when (call.method) {
                "getAppInfo" -> result.success(appInfo())
                "canRequestPackageInstalls" -> result.success(canRequestPackageInstalls())
                "openInstallPermissionSettings" -> {
                    openInstallPermissionSettings()
                    result.success(null)
                }
                "cleanupUpdates" -> {
                    cleanupUpdates(call.requiredLong("currentVersionCode"))
                    result.success(null)
                }
                "startDownload" -> result.success(startDownload(call))
                "getDownloadStatus" ->
                    result.success(downloadStatus(call.requiredLong("downloadId")))
                "launchInstaller" -> launchInstaller(
                    call.requiredLong("downloadId"),
                    result,
                )
                else -> result.notImplemented()
            }
        } catch (error: UpdateException) {
            result.error(error.code, error.message, null)
        } catch (error: Exception) {
            result.error("UPDATE_NATIVE_ERROR", error.message, null)
        }
    }

    private fun appInfo(): Map<String, Any> {
        val info = installedPackageInfo()
        return mapOf(
            "packageName" to info.packageName,
            "versionName" to (info.versionName ?: ""),
            "versionCode" to info.longVersionCodeCompat(),
        )
    }

    private fun canRequestPackageInstalls(): Boolean {
        return Build.VERSION.SDK_INT < Build.VERSION_CODES.O ||
            activity.packageManager.canRequestPackageInstalls()
    }

    private fun openInstallPermissionSettings() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        activity.startActivity(
            Intent(
                Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                Uri.parse("package:${activity.packageName}"),
            ),
        )
    }

    private fun startDownload(call: MethodCall): Long {
        val url = Uri.parse(call.requiredString("url"))
        if (url.scheme != "https" || url.host.isNullOrBlank()) {
            throw UpdateException("DOWNLOAD_URL_INVALID", "Download URL must use HTTPS")
        }
        val meta = DownloadMeta(
            downloadId = 0,
            filePath = updateFile(call.requiredLong("versionCode")).absolutePath,
            sha256 = call.requiredString("sha256").lowercase(),
            sizeBytes = call.requiredLong("sizeBytes"),
            packageName = call.requiredString("packageName"),
            versionCode = call.requiredLong("versionCode"),
        )
        if (!Regex("^[0-9a-f]{64}$").matches(meta.sha256) || meta.sizeBytes <= 0) {
            throw UpdateException("DOWNLOAD_METADATA_INVALID", "Invalid APK metadata")
        }
        findReusableDownload(meta)?.let { return it }
        val destination = File(meta.filePath)
        destination.parentFile?.mkdirs()
        destination.delete()

        val request = DownloadManager.Request(url)
            .setTitle("Echo ${meta.versionCode}")
            .setDescription("正在下载 Echo 更新")
            .setMimeType(APK_MIME_TYPE)
            .setAllowedOverMetered(true)
            .setAllowedOverRoaming(false)
            .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
            .setDestinationUri(Uri.fromFile(destination))
        val downloadId = downloadManager.enqueue(request)
        saveMeta(meta.copy(downloadId = downloadId))
        return downloadId
    }

    private fun downloadStatus(downloadId: Long): Map<String, Any?> {
        val meta = loadMeta(downloadId)
            ?: return failureStatus("DOWNLOAD_NOT_FOUND", "Download metadata is missing")
        val query = DownloadManager.Query().setFilterById(downloadId)
        downloadManager.query(query).use { cursor ->
            if (!cursor.moveToFirst()) {
                return failureStatus("DOWNLOAD_NOT_FOUND", "Download was not found")
            }
            val status = cursor.getInt(cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_STATUS))
            val downloaded = cursor.getLong(
                cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_BYTES_DOWNLOADED_SO_FAR),
            )
            val total = cursor.getLong(
                cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_TOTAL_SIZE_BYTES),
            )
            return when (status) {
                DownloadManager.STATUS_PENDING -> progressStatus("pending", downloaded, total)
                DownloadManager.STATUS_RUNNING,
                DownloadManager.STATUS_PAUSED,
                -> progressStatus("downloading", downloaded, total)
                DownloadManager.STATUS_SUCCESSFUL -> verificationStatus(meta, downloaded, total)
                DownloadManager.STATUS_FAILED -> {
                    val reason = cursor.getInt(
                        cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_REASON),
                    )
                    val code = downloadFailureCode(reason)
                    Log.e(LOG_TAG, "APK download failed: code=$code reason=$reason")
                    failureStatus(code, "DownloadManager reason=$reason")
                }
                else -> failureStatus("DOWNLOAD_FAILED", "Unknown download status=$status")
            }
        }
    }

    private fun verificationStatus(
        meta: DownloadMeta,
        downloaded: Long,
        total: Long,
    ): Map<String, Any?> {
        val task = verificationTasks.computeIfAbsent(meta.downloadId) {
            executor.submit<Unit> { verifyApk(meta) }
        }
        if (!task.isDone) {
            return progressStatus("verifying", downloaded, total)
        }
        try {
            task.get()
        } catch (error: Exception) {
            val cause = error.cause
            discardDownload(meta)
            if (cause is UpdateException) {
                return failureStatus(cause.code, cause.message ?: "APK verification failed")
            }
            return failureStatus("APK_VERIFICATION_FAILED", cause?.message ?: error.message)
        }
        return progressStatus("ready", downloaded, total)
    }

    private fun launchInstaller(downloadId: Long, result: MethodChannel.Result) {
        if (!canRequestPackageInstalls()) {
            result.error(
                "INSTALL_PERMISSION_REQUIRED",
                "Install unknown apps permission is required",
                null,
            )
            return
        }
        val meta = loadMeta(downloadId)
        if (meta == null) {
            result.error("DOWNLOAD_NOT_FOUND", "Download metadata is missing", null)
            return
        }
        executor.execute {
            try {
                verifyApk(meta)
                val apk = File(meta.filePath)
                commitInstallSession(apk, meta)
                activity.runOnUiThread { result.success(null) }
            } catch (error: UpdateException) {
                discardDownload(meta)
                activity.runOnUiThread { result.error(error.code, error.message, null) }
            } catch (error: Exception) {
                Log.e(LOG_TAG, "Unable to create or commit install session", error)
                activity.runOnUiThread {
                    result.error("INSTALL_SESSION_FAILED", error.message, null)
                }
            }
        }
    }

    private fun commitInstallSession(apk: File, meta: DownloadMeta) {
        val installer = activity.packageManager.packageInstaller
        val params = PackageInstaller.SessionParams(
            PackageInstaller.SessionParams.MODE_FULL_INSTALL,
        ).apply {
            setAppPackageName(meta.packageName)
            setSize(meta.sizeBytes)
            setInstallReason(PackageManager.INSTALL_REASON_USER)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                setRequireUserAction(PackageInstaller.SessionParams.USER_ACTION_REQUIRED)
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                setPackageSource(PackageInstaller.PACKAGE_SOURCE_DOWNLOADED_FILE)
            }
        }
        var sessionId: Int? = null
        try {
            sessionId = installer.createSession(params)
            installer.openSession(sessionId).use { session ->
                FileInputStream(apk).use { input ->
                    session.openWrite("base.apk", 0, meta.sizeBytes).use { output ->
                        input.copyTo(output, 1024 * 1024)
                        session.fsync(output)
                    }
                }
                val callbackIntent = Intent(activity, MainActivity::class.java).apply {
                    action = INSTALL_RESULT_ACTION
                    addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP)
                }
                val pendingFlags = PendingIntent.FLAG_UPDATE_CURRENT or
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                        PendingIntent.FLAG_MUTABLE
                    } else {
                        0
                    }
                val callback = PendingIntent.getActivity(
                    activity,
                    sessionId,
                    callbackIntent,
                    pendingFlags,
                )
                session.commit(callback.intentSender)
            }
            Log.i(LOG_TAG, "Install session committed: sessionId=$sessionId")
        } catch (error: Exception) {
            sessionId?.let { id -> runCatching { installer.abandonSession(id) } }
            throw error
        }
    }

    @Suppress("DEPRECATION")
    private fun installConfirmationIntent(intent: Intent): Intent? {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            intent.getParcelableExtra(Intent.EXTRA_INTENT, Intent::class.java)
        } else {
            intent.getParcelableExtra(Intent.EXTRA_INTENT)
        }
    }

    private fun showInstallFailure(message: String) {
        Toast.makeText(activity, "Echo 更新安装失败：$message", Toast.LENGTH_LONG).show()
    }

    private fun verifyApk(meta: DownloadMeta) {
        val apk = File(meta.filePath)
        if (!apk.isFile || apk.length() != meta.sizeBytes) {
            throw UpdateException("APK_SIZE_MISMATCH", "APK size mismatch")
        }
        if (sha256(apk) != meta.sha256) {
            throw UpdateException("APK_HASH_MISMATCH", "APK SHA-256 mismatch")
        }
        val archive = archivePackageInfo(apk)
            ?: throw UpdateException("APK_PACKAGE_INVALID", "APK package metadata is unavailable")
        if (archive.packageName != meta.packageName || archive.packageName != activity.packageName) {
            throw UpdateException("APK_PACKAGE_MISMATCH", "APK package name mismatch")
        }
        val currentVersion = installedPackageInfo().longVersionCodeCompat()
        if (archive.longVersionCodeCompat() != meta.versionCode || meta.versionCode <= currentVersion) {
            throw UpdateException("APK_VERSION_INVALID", "APK version does not upgrade this app")
        }
        if (signatures(archive) != signatures(installedPackageInfo())) {
            throw UpdateException("APK_SIGNATURE_MISMATCH", "APK signature mismatch")
        }
    }

    private fun cleanupUpdates(currentVersionCode: Long) {
        updatesDirectory().listFiles()?.forEach { file ->
            val version = Regex("^echo-update-(\\d+)\\.apk$")
                .matchEntire(file.name)
                ?.groupValues
                ?.get(1)
                ?.toLongOrNull()
            if (version == null || version <= currentVersionCode) {
                file.delete()
            }
        }
        val editor = preferences.edit()
        preferences.all.forEach { (key, value) ->
            if (!key.startsWith(META_PREFIX) || value !is String) return@forEach
            val versionCode = runCatching {
                JSONObject(value).getLong("versionCode")
            }.getOrNull()
            if (versionCode == null || versionCode <= currentVersionCode) {
                editor.remove(key)
            }
        }
        editor.apply()
    }

    @Suppress("DEPRECATION")
    private fun installedPackageInfo(): PackageInfo {
        val flags = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            PackageManager.GET_SIGNING_CERTIFICATES
        } else {
            PackageManager.GET_SIGNATURES
        }
        return activity.packageManager.getPackageInfo(activity.packageName, flags)
    }

    @Suppress("DEPRECATION")
    private fun archivePackageInfo(apk: File): PackageInfo? {
        val flags = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            PackageManager.GET_SIGNING_CERTIFICATES
        } else {
            PackageManager.GET_SIGNATURES
        }
        return activity.packageManager.getPackageArchiveInfo(apk.absolutePath, flags)
    }

    @Suppress("DEPRECATION")
    private fun signatures(info: PackageInfo): Set<String> {
        val values = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            val signingInfo = info.signingInfo
                ?: throw UpdateException("APK_SIGNATURE_MISSING", "APK signature is missing")
            if (signingInfo.hasMultipleSigners()) {
                signingInfo.apkContentsSigners
            } else {
                signingInfo.signingCertificateHistory
            }
        } else {
            info.signatures
                ?: throw UpdateException("APK_SIGNATURE_MISSING", "APK signature is missing")
        }
        return values.map { signature -> digest(signature.toByteArray()) }.toSet()
    }

    private fun sha256(file: File): String {
        val messageDigest = MessageDigest.getInstance("SHA-256")
        FileInputStream(file).use { input ->
            val buffer = ByteArray(1024 * 1024)
            while (true) {
                val count = input.read(buffer)
                if (count <= 0) break
                messageDigest.update(buffer, 0, count)
            }
        }
        return messageDigest.digest().toHex()
    }

    private fun digest(bytes: ByteArray): String {
        return MessageDigest.getInstance("SHA-256").digest(bytes).toHex()
    }

    private fun ByteArray.toHex(): String = joinToString("") { "%02x".format(it) }

    private fun updateFile(versionCode: Long): File {
        return File(updatesDirectory(), "echo-update-$versionCode.apk")
    }

    private fun updatesDirectory(): File {
        val root = activity.getExternalFilesDir(null)
            ?: throw UpdateException("STORAGE_UNAVAILABLE", "External app storage is unavailable")
        return File(root, "updates").apply { mkdirs() }
    }

    private fun saveMeta(meta: DownloadMeta) {
        preferences.edit().putString(
            "$META_PREFIX${meta.downloadId}",
            JSONObject()
                .put("downloadId", meta.downloadId)
                .put("filePath", meta.filePath)
                .put("sha256", meta.sha256)
                .put("sizeBytes", meta.sizeBytes)
                .put("packageName", meta.packageName)
                .put("versionCode", meta.versionCode)
                .toString(),
        ).apply()
    }

    private fun loadMeta(downloadId: Long): DownloadMeta? {
        val raw = preferences.getString("$META_PREFIX$downloadId", null) ?: return null
        return parseMeta(raw)
    }

    private fun findReusableDownload(expected: DownloadMeta): Long? {
        preferences.all.forEach { (key, value) ->
            if (!key.startsWith(META_PREFIX) || value !is String) return@forEach
            val existing = parseMeta(value) ?: return@forEach
            if (existing.versionCode != expected.versionCode) return@forEach
            val metadataMatches =
                existing.sha256 == expected.sha256 &&
                    existing.sizeBytes == expected.sizeBytes &&
                    existing.packageName == expected.packageName
            if (metadataMatches && isReusableDownload(existing)) {
                return existing.downloadId
            }
            discardDownload(existing)
        }
        return null
    }

    private fun isReusableDownload(meta: DownloadMeta): Boolean {
        val query = DownloadManager.Query().setFilterById(meta.downloadId)
        downloadManager.query(query).use { cursor ->
            if (!cursor.moveToFirst()) return false
            return when (
                cursor.getInt(cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_STATUS))
            ) {
                DownloadManager.STATUS_PENDING,
                DownloadManager.STATUS_RUNNING,
                DownloadManager.STATUS_PAUSED,
                -> true
                DownloadManager.STATUS_SUCCESSFUL -> {
                    val file = File(meta.filePath)
                    file.isFile && file.length() == meta.sizeBytes
                }
                else -> false
            }
        }
    }

    private fun discardDownload(meta: DownloadMeta) {
        verificationTasks.remove(meta.downloadId)
        downloadManager.remove(meta.downloadId)
        File(meta.filePath).delete()
        preferences.edit().remove("$META_PREFIX${meta.downloadId}").apply()
    }

    private fun parseMeta(raw: String): DownloadMeta? {
        return runCatching {
            val json = JSONObject(raw)
            DownloadMeta(
                downloadId = json.getLong("downloadId"),
                filePath = json.getString("filePath"),
                sha256 = json.getString("sha256"),
                sizeBytes = json.getLong("sizeBytes"),
                packageName = json.getString("packageName"),
                versionCode = json.getLong("versionCode"),
            )
        }.getOrNull()
    }

    private fun progressStatus(
        status: String,
        downloaded: Long,
        total: Long,
    ): Map<String, Any?> = mapOf(
        "status" to status,
        "downloadedBytes" to downloaded.coerceAtLeast(0),
        "totalBytes" to total.coerceAtLeast(0),
    )

    private fun failureStatus(code: String, message: String?): Map<String, Any?> = mapOf(
        "status" to "failed",
        "errorCode" to code,
        "error" to (message ?: "unknown"),
        "downloadedBytes" to 0L,
        "totalBytes" to 0L,
    )

    private fun downloadFailureCode(reason: Int): String = when (reason) {
        DownloadManager.ERROR_INSUFFICIENT_SPACE -> "DOWNLOAD_INSUFFICIENT_SPACE"
        DownloadManager.ERROR_DEVICE_NOT_FOUND,
        DownloadManager.ERROR_FILE_ERROR,
        -> "DOWNLOAD_STORAGE_ERROR"
        DownloadManager.ERROR_UNHANDLED_HTTP_CODE,
        DownloadManager.ERROR_HTTP_DATA_ERROR,
        DownloadManager.ERROR_TOO_MANY_REDIRECTS,
        -> "DOWNLOAD_HTTP_ERROR"
        DownloadManager.ERROR_CANNOT_RESUME -> "DOWNLOAD_CANNOT_RESUME"
        else -> "DOWNLOAD_FAILED"
    }
}

private data class DownloadMeta(
    val downloadId: Long,
    val filePath: String,
    val sha256: String,
    val sizeBytes: Long,
    val packageName: String,
    val versionCode: Long,
)

private class UpdateException(val code: String, message: String) : IllegalStateException(message)

private fun PackageInfo.longVersionCodeCompat(): Long {
    @Suppress("DEPRECATION")
    return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) longVersionCode else versionCode.toLong()
}

private fun MethodCall.requiredString(name: String): String {
    val value = argument<String>(name)?.trim().orEmpty()
    if (value.isEmpty()) throw UpdateException("ARGUMENT_INVALID", "$name is required")
    return value
}

private fun MethodCall.requiredLong(name: String): Long {
    val value = argument<Number>(name)?.toLong()
        ?: throw UpdateException("ARGUMENT_INVALID", "$name is required")
    if (value <= 0) throw UpdateException("ARGUMENT_INVALID", "$name must be positive")
    return value
}
