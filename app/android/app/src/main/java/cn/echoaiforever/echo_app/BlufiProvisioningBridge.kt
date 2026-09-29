package cn.echoaiforever.echo_app

import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothProfile
import android.content.Context
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.util.Log
import blufi.espressif.BlufiCallback
import blufi.espressif.BlufiClient
import blufi.espressif.params.BlufiConfigureParams
import blufi.espressif.params.BlufiParameter
import blufi.espressif.response.BlufiStatusResponse
import blufi.espressif.response.BlufiVersionResponse
import org.json.JSONObject

class BlufiProvisioningBridge(
    context: Context,
    private val eventPublisher: (Map<String, Any?>) -> Unit,
) {
    private val appContext = context.applicationContext
    private val mainHandler = Handler(Looper.getMainLooper())
    private var client: BlufiClient? = null
    private var securityReady = false
    private var provisioningCompleted = false
    private var configurationSubmitted = false
    private var wifiConnectionFailed = false
    private var wifiConfigureStartedAtMs = 0L
    private var ambiguousWifiFailureReports = 0
    private var polling = false
    private var currentSsid = ""
    private var pendingConfigureParams: BlufiConfigureParams? = null

    private val statusPoll = object : Runnable {
        override fun run() {
            if (!polling) return
            client?.requestDeviceStatus()
            mainHandler.postDelayed(this, STATUS_POLL_INTERVAL_MS)
        }
    }

    private val gattCallback = object : BluetoothGattCallback() {
        override fun onConnectionStateChange(gatt: BluetoothGatt, status: Int, newState: Int) {
            Log.d(TAG, "gatt stateChange status=$status newState=$newState configurationSubmitted=$configurationSubmitted wifiConnectionFailed=$wifiConnectionFailed")
            when {
                wifiConnectionFailed -> {
                    return
                }

                status != BluetoothGatt.GATT_SUCCESS -> {
                    if (configurationSubmitted && !wifiConnectionFailed) {
                        publishProvisioningSuccess("设备已完成 Wi-Fi 配置，蓝牙已断开")
                    } else {
                        publishFailure("BLE 连接失败，状态码 $status")
                    }
                }

                newState == BluetoothProfile.STATE_CONNECTED -> {
                    publish("connected", "BLE 已连接，正在准备 BluFi")
                }

                newState == BluetoothProfile.STATE_DISCONNECTED -> {
                    if (configurationSubmitted && !wifiConnectionFailed) {
                        publishProvisioningSuccess("设备已完成 Wi-Fi 配置，蓝牙已断开")
                    } else if (!provisioningCompleted) {
                        publish("disconnected", "Echo 已断开蓝牙连接")
                    }
                }
            }
        }
    }

    private val blufiCallback = object : BlufiCallback() {
        override fun onGattPrepared(client: BlufiClient, status: Int, gatt: BluetoothGatt) {
            Log.d(TAG, "onGattPrepared status=$status")
            if (status != STATUS_SUCCESS) {
                publishFailure("BluFi 服务准备失败，错误码 $status")
                return
            }
            publish("negotiating_security", "正在建立 BluFi 加密通道")
            client.negotiateSecurity()
        }

        override fun onNegotiateSecurityResult(client: BlufiClient, status: Int) {
            Log.d(TAG, "onNegotiateSecurityResult status=$status")
            if (status != STATUS_SUCCESS) {
                publishFailure("BluFi 加密协商失败，错误码 $status")
                return
            }
            securityReady = true
            publish("ready", "蓝牙配网已就绪，请填写家庭 Wi-Fi")
        }

        override fun onPostCustomDataResult(client: BlufiClient, status: Int, data: ByteArray?) {
            Log.d(TAG, "onPostCustomDataResult status=$status responseLength=${data?.size ?: 0}")
            if (status != STATUS_SUCCESS) {
                pendingConfigureParams = null
                publishFailure("设备绑定信息发送失败，错误码 $status")
                return
            }
            val params = pendingConfigureParams ?: return
            pendingConfigureParams = null
            submitConfigureParams(client, params)
        }

        override fun onPostConfigureParams(client: BlufiClient, status: Int) {
            Log.d(TAG, "onPostConfigureParams status=$status")
            if (status != STATUS_SUCCESS) {
                configurationSubmitted = false
                publishFailure("Wi-Fi 凭据发送失败，错误码 $status")
                return
            }
            configurationSubmitted = true
            wifiConnectionFailed = false
            publish("wifi_connecting", "凭据已发送，设备正在连接 Wi-Fi")
            startStatusPolling()
        }

        override fun onDeviceStatusResponse(
            client: BlufiClient,
            status: Int,
            response: BlufiStatusResponse?,
        ) {
            Log.d(
                TAG,
                "onDeviceStatusResponse status=$status ${response?.toSafeWifiDebugInfo() ?: "staStatus=-1"}",
            )
            if (status != STATUS_SUCCESS || response == null) {
                if (configurationSubmitted && !wifiConnectionFailed) {
                    publish("wifi_connecting", "设备已收到 Wi-Fi 配置，正在等待联网")
                    return
                }
                publishFailure("读取设备 Wi-Fi 状态失败，错误码 $status")
                return
            }

            when (response.getStaConnectionStatus()) {
                BlufiParameter.STA_CONN_SUCCESS -> {
                    ambiguousWifiFailureReports = 0
                    publishProvisioningSuccess("设备已连接家庭 Wi-Fi")
                }

                BlufiParameter.STA_CONN_CONNECTING -> {
                    ambiguousWifiFailureReports = 0
                    publish("wifi_connecting", "设备正在连接 Wi-Fi")
                }

                BlufiParameter.STA_CONN_FAIL,
                BlufiParameter.STA_CONN_NO_IP,
                -> {
                    if (shouldKeepWaitingForWifi(response)) {
                        publish("wifi_connecting", "设备仍在确认 Wi-Fi 连接")
                        return
                    }
                    wifiConnectionFailed = true
                    publishWifiFailure(
                        "设备连接 Wi-Fi 失败，请检查 SSID 和密码，状态码 ${response.getStaConnectionStatus()}",
                    )
                }
            }
        }

        override fun onDeviceVersionResponse(
            client: BlufiClient,
            status: Int,
            response: BlufiVersionResponse?,
        ) {
            Log.d(TAG, "onDeviceVersionResponse status=$status")
            if (status != STATUS_SUCCESS) {
                publishFailure("读取 BluFi 版本失败，错误码 $status")
            }
        }

        override fun onError(client: BlufiClient, errCode: Int) {
            Log.d(TAG, "onError errCode=$errCode configurationSubmitted=$configurationSubmitted wifiConnectionFailed=$wifiConnectionFailed")
            if (configurationSubmitted && !wifiConnectionFailed) {
                publishProvisioningSuccess("设备已完成 Wi-Fi 配置，蓝牙已断开")
                return
            }
            publishFailure("设备返回 BluFi 错误，错误码 $errCode")
        }
    }

    @SuppressLint("MissingPermission")
    fun start(address: String) {
        require(address.isNotBlank()) { "BLE 设备地址不能为空" }
        close(silent = true)

        val adapter = BluetoothAdapter.getDefaultAdapter()
            ?: throw IllegalStateException("当前设备不支持蓝牙")
        val device = adapter.getRemoteDevice(address)
        val nextClient = BlufiClient(appContext, device)
        nextClient.setGattWriteTimeout(GATT_WRITE_TIMEOUT_MS)
        nextClient.setGattCallback(gattCallback)
        nextClient.setBlufiCallback(blufiCallback)
        client = nextClient
        pendingConfigureParams = null
        configurationSubmitted = false
        wifiConnectionFailed = false
        wifiConfigureStartedAtMs = 0L
        ambiguousWifiFailureReports = 0
        publish("connecting", "正在连接 ${device.name ?: "Echo"}")
        nextClient.connect()
    }

    fun configure(ssid: String, password: String, claimToken: String = "") {
        val cleanSsid = ssid.trim()
        require(cleanSsid.isNotEmpty()) { "Wi-Fi 名称不能为空" }
        check(securityReady) { "BluFi 加密通道尚未就绪" }
        val activeClient = client ?: error("蓝牙设备尚未连接")

        currentSsid = cleanSsid
        val params = BlufiConfigureParams().apply {
            setOpMode(BlufiParameter.OP_MODE_STA)
            setStaSSIDBytes(cleanSsid.toByteArray(Charsets.UTF_8))
            setStaPassword(password)
        }
        val cleanClaimToken = claimToken.trim()
        Log.d(
            TAG,
            "configure ssidLength=${cleanSsid.length} passwordPresent=${password.isNotEmpty()} claimTokenPresent=${cleanClaimToken.isNotEmpty()}",
        )
        if (cleanClaimToken.isNotEmpty()) {
            pendingConfigureParams = params
            publish("binding", "正在通过蓝牙发送设备绑定信息")
            val payload = JSONObject()
                .put("type", "echo_bind")
                .put("version", 1)
                .put("claim_token", cleanClaimToken)
                .toString()
                .toByteArray(Charsets.UTF_8)
            Log.d(TAG, "postCustomData payloadLength=${payload.size}")
            activeClient.postCustomData(payload)
            return
        }
        submitConfigureParams(activeClient, params)
    }

    @SuppressLint("MissingPermission")
    fun close(silent: Boolean = false) {
        val wasCompleted = provisioningCompleted
        polling = false
        mainHandler.removeCallbacks(statusPoll)
        client?.close()
        client = null
        securityReady = false
        provisioningCompleted = false
        configurationSubmitted = false
        wifiConnectionFailed = false
        wifiConfigureStartedAtMs = 0L
        ambiguousWifiFailureReports = 0
        pendingConfigureParams = null
        currentSsid = ""
        if (!silent && !wasCompleted) {
            publish("disconnected", "已断开 Echo")
        }
    }

    private fun submitConfigureParams(activeClient: BlufiClient, params: BlufiConfigureParams) {
        configurationSubmitted = true
        wifiConnectionFailed = false
        wifiConfigureStartedAtMs = SystemClock.elapsedRealtime()
        ambiguousWifiFailureReports = 0
        publish("configuring", "正在通过蓝牙发送 Wi-Fi 配置")
        activeClient.configure(params)
    }

    private fun shouldKeepWaitingForWifi(response: BlufiStatusResponse): Boolean {
        if (!configurationSubmitted) return false
        val hasFailureDetail = response.getConnectionEndReason() != -1 ||
            response.getConnectionMaxRetry() != -1 ||
            response.getConnectionRssi() != WIFI_RSSI_UNKNOWN
        if (hasFailureDetail) return false

        ambiguousWifiFailureReports += 1
        val elapsedMs = SystemClock.elapsedRealtime() - wifiConfigureStartedAtMs
        return elapsedMs in 0 until WIFI_FAILURE_GRACE_MS ||
            ambiguousWifiFailureReports < WIFI_FAILURE_CONFIRM_REPORTS
    }

    private fun startStatusPolling() {
        polling = true
        mainHandler.removeCallbacks(statusPoll)
        mainHandler.post(statusPoll)
    }

    private fun publish(state: String, message: String) {
        Log.d(TAG, "publish state=$state messageLength=${message.length}")
        eventPublisher(
            mapOf(
                "state" to state,
                "message" to message,
                "ssid" to currentSsid,
            ),
        )
    }

    private fun publishFailure(message: String) {
        if (provisioningCompleted) return
        polling = false
        mainHandler.removeCallbacks(statusPoll)
        publish("failure", message)
    }

    private fun publishWifiFailure(message: String) {
        if (provisioningCompleted) return
        polling = false
        mainHandler.removeCallbacks(statusPoll)
        publish("wifi_failed", message)
    }

    private fun publishProvisioningSuccess(message: String) {
        if (provisioningCompleted) return
        polling = false
        mainHandler.removeCallbacks(statusPoll)
        provisioningCompleted = true
        publish("success", message)
    }

    companion object {
        private const val TAG = "EchoBlufi"
        private const val GATT_WRITE_TIMEOUT_MS = 10_000L
        private const val STATUS_POLL_INTERVAL_MS = 1_500L
        private const val WIFI_FAILURE_GRACE_MS = 35_000L
        private const val WIFI_FAILURE_CONFIRM_REPORTS = 3
        private const val WIFI_RSSI_UNKNOWN = -128
    }
}

private fun BlufiStatusResponse.toSafeWifiDebugInfo(): String {
    val reason = getConnectionEndReason()
    val reasonName = when (reason) {
        BlufiParameter.WIFI_REASON_NO_AP_FOUND -> "NO_AP_FOUND"
        BlufiParameter.WIFI_REASON_CONNECTION_FAIL -> "CONNECTION_FAIL"
        BlufiParameter.WIFI_REASON_4WAY_HANDSHAKE_TIMEOUT -> "4WAY_HANDSHAKE_TIMEOUT"
        BlufiParameter.WIFI_REASON_HANDSHAKE_TIMEOUT -> "HANDSHAKE_TIMEOUT"
        -1 -> "N/A"
        else -> "UNKNOWN"
    }
    return "staStatus=${getStaConnectionStatus()} endReason=$reason reason=$reasonName rssi=${getConnectionRssi()} maxRetry=${getConnectionMaxRetry()}"
}
