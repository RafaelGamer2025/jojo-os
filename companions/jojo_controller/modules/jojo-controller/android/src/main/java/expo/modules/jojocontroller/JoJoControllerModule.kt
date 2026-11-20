package expo.modules.jojocontroller

import android.Manifest
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.SystemClock
import android.provider.Settings
import expo.modules.kotlin.Promise
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition
import java.io.IOException
import java.net.Socket
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.Executors
import java.util.concurrent.RejectedExecutionException
import java.util.concurrent.ScheduledThreadPoolExecutor
import java.util.concurrent.ThreadFactory
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicLong

class JoJoControllerModule : Module() {
  private val worker = ScheduledThreadPoolExecutor(1, DaemonThreadFactory("JoJoController"))
    .apply { removeOnCancelPolicy = true }
  private val connector = Executors.newCachedThreadPool(DaemonThreadFactory("JoJoUsbConnect"))
  private val generation = AtomicLong(0L)
  private val foreground = AtomicBoolean(true)
  private val mask = AtomicInteger(0)
  private val maskRefreshedAt = AtomicLong(SystemClock.elapsedRealtime())
  private val pendingSockets = ConcurrentHashMap<Long, Socket>()

  // All transport/session fields below are confined to worker, except the atomics above.
  private var mode = "none"
  private var usbSession: UsbTcpSession? = null
  private val bluetooth by lazy {
    BluetoothHidController(
      contextProvider = { appContext.reactContext },
      worker = worker,
      isSessionCurrent = { session -> foreground.get() && generation.get() == session },
      currentMask = { mask.get() },
      maskAgeMs = { SystemClock.elapsedRealtime() - maskRefreshedAt.get() },
      onStatus = { session, state, message, device ->
        if (isSessionCurrent(session)) emitStatus("bluetooth", state, message, device)
      },
      onTerminal = { session, state, message, device -> finishSession(session, state, message, device) }
    )
  }

  override fun definition() = ModuleDefinition {
    Name("JoJoController")
    Events("onStatus")

    AsyncFunction("capabilities") {
      val adapter = bluetoothAdapter()
      val hasConnect = hasBluetoothConnectPermission()
      val enabled = if (adapter == null || (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && !hasConnect)) {
        false
      } else {
        try { adapter.isEnabled } catch (_: SecurityException) { false }
      }
      mapOf(
        "androidApi" to Build.VERSION.SDK_INT,
        "bluetoothEnabled" to enabled,
        "hidApiAvailable" to (Build.VERSION.SDK_INT >= 28 && adapter != null)
      )
    }

    AsyncFunction("listBondedDevices") {
      if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && !hasBluetoothConnectPermission()) {
        throw SecurityException("BLUETOOTH_CONNECT permission must be granted before listing bonded devices")
      }
      val devices = bluetoothAdapter()?.bondedDevices ?: emptySet()
      devices.map { device ->
        val address = device.address
        mapOf("name" to (device.name ?: address), "address" to address)
      }
    }

    AsyncFunction("startBluetooth") { address: String, promise: Promise ->
      val normalized = normalizeBluetoothAddress(address)
      val queued = enqueue {
        if (!foreground.get()) {
          emitStatus("none", "error", "Cannot start Bluetooth while the app is in the background")
          return@enqueue
        }
        val session = beginSession("bluetooth")
        if (Build.VERSION.SDK_INT < 28) {
          finishSession(session, "error", "Bluetooth HID Device requires Android API 28 or newer", normalized)
          return@enqueue
        }
        emitStatus("bluetooth", "connecting", "Opening Bluetooth HID profile", normalized)
        bluetooth.start(normalized, session)
      }
      // Resolves when the command is queued; registration/connection are reported by onStatus.
      if (queued) promise.resolve(null)
      else promise.reject("E_CANCELLED", "Controller module was destroyed")
      Unit
    }

    AsyncFunction("connectUsb") { token: String, promise: Promise ->
      if (!Regex("^[0-9a-f]{32}$").matches(token)) {
        promise.reject("E_USB_TOKEN", "USB token must be exactly 32 lowercase hexadecimal characters")
        return@AsyncFunction
      }
      if (!foreground.get()) {
        promise.reject("E_BACKGROUND", "USB controller cannot connect while the app is in the background")
        return@AsyncFunction
      }
      val settled = AtomicBoolean(false)
      try {
        worker.execute startUsb@{
          if (!foreground.get()) {
            rejectOnce(settled, promise, "E_BACKGROUND", "USB controller cannot connect while the app is in the background")
            return@startUsb
          }
          val session = beginSession("usb")
          emitStatus("usb", "connecting", "Connecting to USB bridge at 127.0.0.1:8765")
          val candidate = Socket()
          pendingSockets[session] = candidate
          try {
            connector.execute doHandshake@{
              try {
                if (!isSessionCurrent(session)) throw IOException("USB connection was cancelled")
                val connectedSocket = UsbTcpSession.connectAndHandshake(token, candidate)
                worker.execute handshakeComplete@{
                  pendingSockets.remove(session, candidate)
                  if (!isSessionCurrent(session)) {
                    closeQuietly(connectedSocket)
                    rejectOnce(settled, promise, "E_CANCELLED", "USB connection was cancelled")
                    return@handshakeComplete
                  }
                  val transport = UsbTcpSession(
                    socket = connectedSocket,
                    worker = worker,
                    currentMask = { mask.get() },
                    lastMaskRefreshMs = { maskRefreshedAt.get() },
                    onPeerLost = { message -> enqueue { finishSession(session, "disconnected", message) } }
                  )
                  usbSession = transport
                  transport.start()
                  emitStatus("usb", "connected", "USB TCP handshake completed", "127.0.0.1:8765")
                  if (transportIsCurrent(session)) {
                    if (settled.compareAndSet(false, true)) promise.resolve(null)
                  } else {
                    rejectOnce(settled, promise, "E_USB_CONNECT", "USB transport failed during startup")
                  }
                }
              } catch (error: Throwable) {
                pendingSockets.remove(session, candidate)
                closeQuietly(candidate)
                try {
                  worker.execute handshakeFailure@{
                    if (isSessionCurrent(session)) {
                      finishSession(session, "error", "USB handshake failed: ${error.message ?: error.javaClass.simpleName}")
                    }
                    rejectOnce(settled, promise, "E_USB_CONNECT", error.message ?: "USB handshake failed", error)
                  }
                } catch (_: RejectedExecutionException) {
                  rejectOnce(settled, promise, "E_CANCELLED", "Controller module was destroyed", error)
                }
              }
            }
          } catch (error: RejectedExecutionException) {
            pendingSockets.remove(session, candidate)
            closeQuietly(candidate)
            finishSession(session, "error", "USB connector is unavailable")
            rejectOnce(settled, promise, "E_USB_CONNECT", "USB connector is unavailable", error)
          }
        }
      } catch (error: RejectedExecutionException) {
        rejectOnce(settled, promise, "E_CANCELLED", "Controller module was destroyed", error)
      }
    }

    Function("setMask") { newMask: Int ->
      require(newMask in 0..JoJoGamepadReport.MASK_MAX) { "Mask must be an integer in 0..2047" }
      mask.set(newMask)
      maskRefreshedAt.set(SystemClock.elapsedRealtime())
      enqueue {
        usbSession?.onMaskRefreshed(newMask)
        if (Build.VERSION.SDK_INT >= 28 && mode == "bluetooth") {
          bluetooth.onMaskRefreshed()
        }
      }
      Unit
    }

    AsyncFunction("disconnect") { promise: Promise ->
      enqueue(
        onRejected = { promise.reject("E_CANCELLED", "Controller module was destroyed") }
      ) {
        stopSession()
        emitStatus("none", "disconnected", "Controller disconnected")
        promise.resolve(null)
      }
    }

    AsyncFunction("openBluetoothSettings") {
      val context = appContext.reactContext ?: throw IllegalStateException("Android context is unavailable")
      context.startActivity(Intent(Settings.ACTION_BLUETOOTH_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
      Unit
    }

    OnActivityEntersBackground {
      foreground.set(false)
      enqueue {
        if (mode != "none") {
          stopSession()
          emitStatus("none", "disconnected", "Controller released because the app entered the background")
        } else {
          stopSession()
        }
      }
    }

    OnActivityEntersForeground {
      foreground.set(true)
    }

    OnDestroy {
      foreground.set(false)
      enqueue(
        onRejected = { shutdownExecutors() }
      ) {
        stopSession()
        shutdownExecutors()
      }
    }
  }

  private fun beginSession(nextMode: String): Long {
    val previousMode = mode
    generation.incrementAndGet() // invalidate all callbacks and connector results from the old session
    closeActiveTransports()
    if (previousMode != "none") emitStatus("none", "disconnected", "Previous controller session closed")
    mode = nextMode
    return generation.get()
  }

  private fun stopSession() {
    generation.incrementAndGet()
    closeActiveTransports()
    mode = "none"
  }

  private fun closeActiveTransports() {
    pendingSockets.values.forEach(::closeQuietly)
    pendingSockets.clear()
    usbSession?.close()
    usbSession = null
    if (Build.VERSION.SDK_INT >= 28) bluetooth.stop()
    mask.set(0)
    maskRefreshedAt.set(SystemClock.elapsedRealtime())
  }

  private fun finishSession(session: Long, state: String, message: String, device: String? = null) {
    if (!isSessionCurrent(session)) return
    generation.compareAndSet(session, session + 1)
    closeActiveTransports()
    mode = "none"
    emitStatus("none", state, message, device)
  }

  private fun emitStatus(statusMode: String, state: String, message: String, device: String? = null) {
    val payload = mutableMapOf<String, Any>(
      "mode" to statusMode,
      "state" to state,
      "message" to message
    )
    if (device != null) payload["device"] = device
    sendEvent("onStatus", payload)
  }

  private fun isSessionCurrent(session: Long): Boolean =
    foreground.get() && generation.get() == session

  private fun transportIsCurrent(session: Long): Boolean =
    isSessionCurrent(session) && mode == "usb" && usbSession != null

  private fun normalizeBluetoothAddress(address: String): String {
    val normalized = address.trim().uppercase()
    require(Regex("^[0-9A-F]{2}(:[0-9A-F]{2}){5}$").matches(normalized)) {
      "Bluetooth address must be a MAC address from listBondedDevices()"
    }
    return normalized
  }

  private fun bluetoothAdapter(): BluetoothAdapter? {
    return try {
      val context = appContext.reactContext
      if (context == null) null
      else (context.getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager)?.adapter
    } catch (_: Exception) {
      null
    }
  }

  private fun hasBluetoothConnectPermission(): Boolean {
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) return true
    val context = appContext.reactContext ?: return false
    return context.checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) == PackageManager.PERMISSION_GRANTED
  }

  private fun rejectOnce(
    settled: AtomicBoolean,
    promise: Promise,
    code: String,
    message: String,
    cause: Throwable? = null
  ) {
    if (settled.compareAndSet(false, true)) promise.reject(code, message, cause)
  }

  private fun closeQuietly(socket: Socket) {
    try { socket.close() } catch (_: IOException) {}
  }

  private fun enqueue(onRejected: (() -> Unit)? = null, task: () -> Unit): Boolean {
    try {
      worker.execute(task)
      true
    } catch (_: RejectedExecutionException) {
      onRejected?.invoke()
      false
    }
  }

  private fun shutdownExecutors() {
    connector.shutdownNow()
    worker.shutdown()
  }

  private class DaemonThreadFactory(private val prefix: String) : ThreadFactory {
    private val sequence = AtomicInteger(0)
    override fun newThread(task: Runnable): Thread = Thread(task, "$prefix-${sequence.incrementAndGet()}").apply {
      isDaemon = true
    }
  }
}
