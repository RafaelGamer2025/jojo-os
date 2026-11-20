package expo.modules.jojocontroller

import android.Manifest
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothHidDevice
import android.bluetooth.BluetoothHidDeviceAppSdpSettings
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import java.util.concurrent.ScheduledThreadPoolExecutor
import java.util.concurrent.ScheduledFuture
import java.util.concurrent.TimeUnit

/**
 * API-28+ Android HID Device profile. This class is loaded lazily only after the API-level check
 * in JoJoControllerModule, keeping BluetoothHidDevice out of the module's Android-24 code path.
 * All state and HID report writes run on the module's one serial worker.
 */
@Suppress("DEPRECATION")
internal class BluetoothHidController(
  private val contextProvider: () -> Context?,
  private val worker: ScheduledThreadPoolExecutor,
  private val isSessionCurrent: (Long) -> Boolean,
  private val currentMask: () -> Int,
  private val maskAgeMs: () -> Long,
  private val onStatus: (Long, String, String, String?) -> Unit,
  private val onTerminal: (Long, String, String, String?) -> Unit
) {
  private var session = -1L
  private var adapter: BluetoothAdapter? = null
  private var hid: BluetoothHidDevice? = null
  private var target: BluetoothDevice? = null
  private var targetAddress: String? = null
  private var registered = false
  private var registrationPending = false
  private var connectRequested = false
  private var connected = false
  private var lastReportMask: Int? = null
  private var reportLoopStopped = false
  private var registrationTimeout: ScheduledFuture<*>? = null
  private var reportTick: ScheduledFuture<*>? = null

  fun start(address: String, generation: Long) {
    session = generation
    targetAddress = address
    val context = contextProvider() ?: return terminal(generation, "error", "Android context is unavailable")
    try {
      requireConnectPermission(context)
      val manager = context.getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager
        ?: return terminal(generation, "error", "Bluetooth is not available on this device")
      val foundAdapter = manager.adapter
        ?: return terminal(generation, "error", "Bluetooth is not available on this device")
      if (!foundAdapter.isEnabled) return terminal(generation, "error", "Bluetooth is turned off")
      adapter = foundAdapter
      target = foundAdapter.getRemoteDevice(address)

      // Capture generation and adapter in this listener. Never consult mutable `session` for an
      // old listener: a late Android callback must not become current after a new startBluetooth.
      val listener = object : BluetoothProfile.ServiceListener {
        override fun onServiceConnected(profile: Int, proxy: BluetoothProfile) {
          val hidProxy = proxy as? BluetoothHidDevice
          if (!isCurrent(generation)) {
            closeLateProfile(foundAdapter, profile, proxy)
            return
          }
          try {
            worker.execute {
              if (!isCurrent(generation)) {
                closeLateProfile(foundAdapter, profile, proxy)
              } else if (profile != BluetoothProfile.HID_DEVICE || hidProxy == null) {
                terminal(generation, "error", "Android did not provide the HID Device profile")
              } else {
                register(hidProxy, generation)
              }
            }
          } catch (_: RuntimeException) {
            closeLateProfile(foundAdapter, profile, proxy)
          }
        }

        override fun onServiceDisconnected(profile: Int) {
          if (!isCurrent(generation)) return
          post {
            if (isCurrent(generation)) terminal(generation, "disconnected", "Bluetooth HID profile disconnected")
          }
        }
      }
      val accepted = foundAdapter.getProfileProxy(context, listener, BluetoothProfile.HID_DEVICE)
      if (!accepted) {
        terminal(generation, "error", "Android refused the Bluetooth HID profile request")
      } else {
        // Covers both a missing profile callback and a registration callback that never arrives.
        registrationTimeout = worker.schedule({
          if (isCurrent(generation) && !registered) {
            terminal(generation, "error", "Timed out waiting for Bluetooth HID profile/registration")
          }
        }, REGISTRATION_TIMEOUT_SECONDS, TimeUnit.SECONDS)
      }
    } catch (error: SecurityException) {
      terminal(generation, "error", "Bluetooth permission is missing: ${error.message ?: "BLUETOOTH_CONNECT required"}")
    } catch (error: Exception) {
      terminal(generation, "error", "Could not start Bluetooth HID: ${error.message ?: error.javaClass.simpleName}")
    }
  }

  /** Called on the serial worker after a JS setMask refresh. */
  fun onMaskRefreshed() {
    if (!isCurrent() || !connected) return
    val mask = freshMask()
    if (reportLoopStopped) {
      reportLoopStopped = false
      sendMask(mask)
      scheduleReportTick()
    } else if (lastReportMask != mask) {
      sendMask(mask)
    }
  }

  /** Best-effort neutral report, disconnect, unregister, and close the profile proxy. */
  fun stop() {
    registrationTimeout?.cancel(false)
    registrationTimeout = null
    reportTick?.cancel(false)
    reportTick = null
    val oldHid = hid
    val oldTarget = target
    val oldAdapter = adapter
    if (oldHid != null) {
      try {
        if (connected && registered && oldTarget != null) {
          oldHid.sendReport(oldTarget, JoJoGamepadReport.REPORT_ID.toInt(), JoJoGamepadReport.encode(0))
          oldHid.disconnect(oldTarget)
        }
      } catch (_: Exception) {
      }
      try {
        if (registered) oldHid.unregisterApp()
      } catch (_: Exception) {
      }
      try {
        oldAdapter?.closeProfileProxy(BluetoothProfile.HID_DEVICE, oldHid)
      } catch (_: Exception) {
      }
    }
    hid = null
    target = null
    targetAddress = null
    adapter = null
    registered = false
    registrationPending = false
    connectRequested = false
    connected = false
    lastReportMask = null
    reportLoopStopped = false
    session = -1L
  }

  private fun register(proxy: BluetoothHidDevice, generation: Long) {
    if (!isCurrent(generation)) {
      adapter?.let { closeLateProfile(it, BluetoothProfile.HID_DEVICE, proxy) }
      return
    }
    hid = proxy
    val callback = object : BluetoothHidDevice.Callback() {
      override fun onAppStatusChanged(pluggedDevice: BluetoothDevice?, appRegistered: Boolean) {
        if (!isCurrent(generation)) return
        if (!appRegistered) {
          if (registrationPending || registered) {
            terminal(generation, "error", "Android did not register the Bluetooth HID gamepad")
          }
          return
        }
        registrationPending = false
        registered = true
        registrationTimeout?.cancel(false)
        registrationTimeout = null
        onStatus(generation, "registered", "Bluetooth HID gamepad registered; waiting for host connection", targetAddress)
        val selected = target ?: return terminal(generation, "error", "Selected Bluetooth device is unavailable")
        try {
          connectRequested = true
          if (!proxy.connect(selected)) {
            terminal(generation, "error", "Android refused the Bluetooth HID connection request")
          }
        } catch (error: Exception) {
          terminal(generation, "error", "Bluetooth HID connect failed: ${error.message ?: error.javaClass.simpleName}")
        }
      }

      override fun onConnectionStateChanged(device: BluetoothDevice, state: Int) {
        if (!isCurrent(generation)) return
        if (!isSelected(device)) {
          try { proxy.disconnect(device) } catch (_: Exception) {}
          return
        }
        when (state) {
          BluetoothProfile.STATE_CONNECTING ->
            onStatus(generation, "connecting", "Connecting to paired Bluetooth host", targetAddress)
          BluetoothProfile.STATE_CONNECTED -> {
            connected = true
            reportLoopStopped = false
            onStatus(generation, "connected", "Bluetooth HID host connected", targetAddress)
            sendMask(freshMask())
            if (isCurrent(generation) && connected && maskAgeMs() < WATCHDOG_MS) {
              scheduleReportTick()
            } else if (isCurrent(generation) && connected) {
              releaseAndStopReports()
            }
          }
          BluetoothProfile.STATE_DISCONNECTED -> {
            if (connectRequested || connected) {
              connected = false
              terminal(generation, "disconnected", "Bluetooth HID host disconnected")
            }
          }
        }
      }

      override fun onGetReport(device: BluetoothDevice, type: Byte, id: Byte, bufferSize: Int) {
        if (!isCurrent(generation)) return
        if (!isSelected(device)) return reportError(proxy, device, ERR_UNSUPPORTED)
        if (id != JoJoGamepadReport.REPORT_ID) return reportError(proxy, device, ERR_INVALID_REPORT_ID)
        if (type != JoJoGamepadReport.REPORT_TYPE_INPUT) return reportError(proxy, device, ERR_UNSUPPORTED)
        try {
          proxy.replyReport(device, type, id, JoJoGamepadReport.encode(freshMask()))
        } catch (_: Exception) {
          reportError(proxy, device, ERR_UNSUPPORTED)
        }
      }

      override fun onSetReport(device: BluetoothDevice, type: Byte, id: Byte, data: ByteArray) {
        if (!isCurrent(generation)) return
        if (!isSelected(device)) return reportError(proxy, device, ERR_UNSUPPORTED)
        reportError(proxy, device, if (id == JoJoGamepadReport.REPORT_ID) ERR_UNSUPPORTED else ERR_INVALID_REPORT_ID)
      }

      override fun onSetProtocol(device: BluetoothDevice, protocol: Byte) {
        if (!isCurrent(generation) || !isSelected(device)) return
        if (protocol != PROTOCOL_REPORT_MODE) {
          reportError(proxy, device, ERR_UNSUPPORTED)
          // A gamepad has no keyboard/mouse boot report. Do not silently send a wrong layout.
          terminal(generation, "error", "Bluetooth host requested unsupported HID boot protocol; disconnected")
        }
      }

      override fun onInterruptData(device: BluetoothDevice, reportId: Byte, data: ByteArray) {
        if (!isCurrent(generation)) return
        if (!isSelected(device)) return reportError(proxy, device, ERR_UNSUPPORTED)
        reportError(proxy, device, if (reportId == JoJoGamepadReport.REPORT_ID) ERR_UNSUPPORTED else ERR_INVALID_REPORT_ID)
      }

      override fun onVirtualCableUnplug(device: BluetoothDevice) {
        if (isCurrent(generation) && isSelected(device)) {
          terminal(generation, "disconnected", "Bluetooth host unplugged the HID gamepad")
        }
      }
    }

    registrationPending = true
    val sdp = BluetoothHidDeviceAppSdpSettings(
      "JoJo Controller",
      "JoJoControl HID gamepad",
      "JoJoControl",
      GAMEPAD_SUBCLASS,
      JoJoGamepadReport.DESCRIPTOR
    )
    try {
      if (!proxy.registerApp(sdp, null, null, worker, callback)) {
        terminal(generation, "error", "Android refused to register the Bluetooth HID gamepad")
      }
    } catch (error: Exception) {
      terminal(generation, "error", "Bluetooth HID registration failed: ${error.message ?: error.javaClass.simpleName}")
    }
  }

  private fun scheduleReportTick() {
    if (!isCurrent() || !connected || reportLoopStopped || reportTick != null) return
    val generation = session
    reportTick = worker.schedule({
      reportTick = null
      if (!isCurrent(generation) || !connected) return@schedule
      if (maskAgeMs() >= WATCHDOG_MS) {
        releaseAndStopReports()
        return@schedule
      }
      sendMask(freshMask())
      scheduleReportTick()
    }, REPORT_PERIOD_MS, TimeUnit.MILLISECONDS)
  }

  private fun releaseAndStopReports() {
    if (lastReportMask != 0) sendMask(0)
    reportLoopStopped = true
    reportTick?.cancel(false)
    reportTick = null
  }

  private fun sendMask(mask: Int) {
    val proxy = hid ?: return
    val selected = target ?: return
    if (!isCurrent() || !connected || !registered) return
    try {
      if (!proxy.sendReport(selected, JoJoGamepadReport.REPORT_ID.toInt(), JoJoGamepadReport.encode(mask))) {
        terminal(session, "error", "Android could not send the Bluetooth HID gamepad report")
        return
      }
      lastReportMask = mask
    } catch (error: Exception) {
      terminal(session, "error", "Bluetooth HID report failed: ${error.message ?: error.javaClass.simpleName}")
    }
  }

  private fun freshMask(): Int =
    if (maskAgeMs() < WATCHDOG_MS) currentMask().coerceIn(0, JoJoGamepadReport.MASK_MAX) else 0

  private fun isSelected(device: BluetoothDevice): Boolean = try {
    device.address.equals(targetAddress, ignoreCase = true)
  } catch (_: SecurityException) {
    false
  }

  private fun reportError(proxy: BluetoothHidDevice, device: BluetoothDevice, code: Byte) {
    try { proxy.reportError(device, code) } catch (_: Exception) {}
  }

  private fun requireConnectPermission(context: Context) {
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S &&
      context.checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) != PackageManager.PERMISSION_GRANTED
    ) {
      throw SecurityException("BLUETOOTH_CONNECT must be granted by the app")
    }
  }

  private fun isCurrent(): Boolean = isCurrent(session)

  private fun isCurrent(generation: Long): Boolean =
    generation >= 0L && session == generation && isSessionCurrent(generation)

  private fun terminal(state: String, message: String) = terminal(session, state, message)

  private fun terminal(generation: Long, state: String, message: String) {
    if (isCurrent(generation)) onTerminal(generation, state, message, targetAddress)
  }

  private fun closeLateProfile(adapter: BluetoothAdapter, profile: Int, proxy: BluetoothProfile) {
    try { adapter.closeProfileProxy(profile, proxy) } catch (_: Exception) {}
  }

  private fun post(block: () -> Unit) {
    try { worker.execute(block) } catch (_: RuntimeException) {}
  }

  companion object {
    private const val WATCHDOG_MS = 300L
    private const val REPORT_PERIOD_MS = 100L
    private const val REGISTRATION_TIMEOUT_SECONDS = 15L
    private const val PROTOCOL_REPORT_MODE: Byte = 1
    private const val GAMEPAD_SUBCLASS: Byte = 0x05
    private const val ERR_UNSUPPORTED: Byte = 3
    private const val ERR_INVALID_REPORT_ID: Byte = 2
  }
}
