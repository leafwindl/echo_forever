package cn.echoaiforever.echo_app

import com.ryanheise.audioservice.AudioServiceActivity
import io.flutter.embedding.engine.FlutterEngine

class MainActivity : AudioServiceActivity() {
    private lateinit var directUpdatePlugin: DirectUpdatePlugin

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        directUpdatePlugin = DirectUpdatePlugin(this)
        directUpdatePlugin.register(flutterEngine.dartExecutor.binaryMessenger)
    }

    override fun onDestroy() {
        if (::directUpdatePlugin.isInitialized) {
            directUpdatePlugin.dispose()
        }
        super.onDestroy()
    }
}
