package cn.echoaiforever.echo_app

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Intent
import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.net.wifi.WifiConfiguration
import android.net.wifi.WifiNetworkSpecifier
import android.os.Build
import android.os.Bundle
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    private val wifiChannelName = "echo/device_wifi"
    private var wifiCallback: ConnectivityManager.NetworkCallback? = null
    private var wifiNetwork: Network? = null
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
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, wifiChannelName).setMethodCallHandler { call, result ->
            when (call.method) {
                "connectToHotspot" -> connectToHotspot(call.argument<String>("ssid"), result)
                "disconnect" -> disconnectFromHotspot(result)
                "openWifiSettings" -> {
                    startActivity(Intent(android.provider.Settings.ACTION_WIFI_SETTINGS))
                    result.success(null)
                }
                else -> result.notImplemented()
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        if (::directUpdatePlugin.isInitialized) {
            directUpdatePlugin.handleInstallResult(intent)
        }
    }

    override fun onDestroy() {
        disconnectFromHotspot(null)
        if (::directUpdatePlugin.isInitialized) {
            directUpdatePlugin.dispose()
        }
        super.onDestroy()
    }

    private fun connectToHotspot(ssid: String?, result: MethodChannel.Result) {
        if (ssid.isNullOrBlank()) {
            result.error("INVALID_SSID", "热点名称不能为空", null)
            return
        }
        val connectivity = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        disconnectFromHotspot(null)
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) {
            @Suppress("DEPRECATION")
            val wifi = getSystemService(Context.WIFI_SERVICE) as android.net.wifi.WifiManager
            @Suppress("DEPRECATION")
            val config = WifiConfiguration().apply { SSID = "\"$ssid\"" }
            @Suppress("DEPRECATION")
            val id = wifi.addNetwork(config)
            @Suppress("DEPRECATION")
            if (id >= 0 && wifi.enableNetwork(id, true)) result.success(true)
            else result.error("WIFI_CONNECT_FAILED", "无法连接设备热点", null)
            return
        }
        val specifier = WifiNetworkSpecifier.Builder().setSsid(ssid).build()
        val request = NetworkRequest.Builder()
            .addTransportType(NetworkCapabilities.TRANSPORT_WIFI)
            // The device SoftAP is intentionally local-only. Removing the
            // INTERNET capability prevents Android captive-portal detection
            // from opening a browser sign-in page for 192.168.4.1.
            .removeCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
            .setNetworkSpecifier(specifier)
            .build()
        val callback = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) {
                wifiNetwork = network
                connectivity.bindProcessToNetwork(network)
                runOnUiThread { result.success(true) }
            }

            override fun onUnavailable() {
                runOnUiThread { result.error("WIFI_CONNECT_FAILED", "无法连接设备热点，请确认热点名称和设备状态", null) }
                wifiCallback = null
            }
        }
        wifiCallback = callback
        connectivity.requestNetwork(request, callback)
    }

    private fun disconnectFromHotspot(result: MethodChannel.Result?) {
        val connectivity = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        connectivity.bindProcessToNetwork(null)
        wifiCallback?.let {
            runCatching { connectivity.unregisterNetworkCallback(it) }
        }
        wifiCallback = null
        wifiNetwork = null
        result?.success(null)
    }
}
