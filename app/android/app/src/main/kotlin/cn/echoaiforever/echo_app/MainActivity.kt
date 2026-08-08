package cn.echoaiforever.echo_app

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Intent
import android.os.Build
import android.os.Bundle
import com.ryanheise.audioservice.AudioServiceActivity
import io.flutter.embedding.engine.FlutterEngine

class MainActivity : AudioServiceActivity() {
    private lateinit var directUpdatePlugin: DirectUpdatePlugin

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                "echo_messages",
                "Echo messages",
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Echo proactive messages and reminders"
            }
            getSystemService(NotificationManager::class.java)?.createNotificationChannel(channel)
        }
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        directUpdatePlugin = DirectUpdatePlugin(this)
        directUpdatePlugin.register(flutterEngine.dartExecutor.binaryMessenger)
        directUpdatePlugin.handleInstallResult(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        if (::directUpdatePlugin.isInitialized) {
            directUpdatePlugin.handleInstallResult(intent)
        }
    }

    override fun onDestroy() {
        if (::directUpdatePlugin.isInitialized) {
            directUpdatePlugin.dispose()
        }
        super.onDestroy()
    }
}
