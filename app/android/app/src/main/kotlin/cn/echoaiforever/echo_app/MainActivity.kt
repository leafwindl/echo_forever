package cn.echoaiforever.echo_app

import android.content.Intent
import com.ryanheise.audioservice.AudioServiceActivity
import io.flutter.embedding.engine.FlutterEngine

class MainActivity : AudioServiceActivity() {
    private lateinit var directUpdatePlugin: DirectUpdatePlugin

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
