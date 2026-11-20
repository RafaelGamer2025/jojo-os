package expo.modules.jojocontroller

import android.os.SystemClock
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.EOFException
import java.io.IOException
import java.net.InetSocketAddress
import java.net.Socket
import java.nio.charset.StandardCharsets
import java.util.concurrent.ScheduledThreadPoolExecutor
import java.util.concurrent.ScheduledFuture
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

/**
 * A connected USB-over-ADB-reverse session. All writes and timer state changes are invoked on
 * the module's single-thread ScheduledThreadPoolExecutor; the reader thread only watches EOF.
 */
internal class UsbTcpSession(
  private val socket: Socket,
  private val worker: ScheduledThreadPoolExecutor,
  private val currentMask: () -> Int,
  private val lastMaskRefreshMs: () -> Long,
  private val onPeerLost: (String) -> Unit
) {
  private val closed = AtomicBoolean(false)
  private var tick: ScheduledFuture<*>? = null
  private var heartbeatStopped = false
  private var lastSentMask: Int? = null

  fun start() {
    if (closed.get()) return
    startReader()
    val fresh = isFresh()
    sendMask(if (fresh) currentMask() else 0)
    heartbeatStopped = !fresh
    if (!heartbeatStopped) scheduleTick()
  }

  /** Called on the serial worker after every JS refresh. */
  fun onMaskRefreshed(mask: Int) {
    if (closed.get()) return
    val fresh = isFresh()
    if (!fresh) return
    if (heartbeatStopped) {
      heartbeatStopped = false
      sendMask(mask)
      scheduleTick()
    } else if (lastSentMask != mask) {
      sendMask(mask)
    }
  }

  /** Best-effort release before closing on explicit disconnect/background/destroy. */
  fun close() {
    if (!closed.get()) {
      try {
        if (lastSentMask != null && lastSentMask != 0) writeMask(0)
      } catch (_: IOException) {
        // The peer may already have closed. Closing the socket is still the release boundary.
      }
      closed.set(true)
    }
    tick?.cancel(false)
    tick = null
    try {
      socket.close()
    } catch (_: IOException) {
    }
  }

  private fun scheduleTick() {
    if (closed.get() || heartbeatStopped || tick != null) return
    tick = worker.schedule({
      tick = null
      if (closed.get()) return@schedule
      if (!isFresh()) {
        // Release once, then stop transmitting entirely until JS refreshes again.
        if (lastSentMask != 0) sendMask(0)
        heartbeatStopped = true
        return@schedule
      }
      sendMask(currentMask())
      scheduleTick()
    }, 100, TimeUnit.MILLISECONDS)
  }

  private fun isFresh(): Boolean =
    SystemClock.elapsedRealtime() - lastMaskRefreshMs() < WATCHDOG_MS

  private fun sendMask(mask: Int) {
    if (closed.get() || mask !in 0..JoJoGamepadReport.MASK_MAX) return
    try {
      writeMask(mask)
    } catch (error: IOException) {
      if (closed.compareAndSet(false, true)) {
        tick?.cancel(false)
        tick = null
        try { socket.close() } catch (_: IOException) {}
        onPeerLost("USB write failed: ${error.message ?: "socket error"}")
      }
    }
  }

  @Throws(IOException::class)
  private fun writeMask(mask: Int) {
    val frame = "{\"mask\":$mask}\n".toByteArray(StandardCharsets.UTF_8)
    if (frame.size > MAX_LINE_BYTES) throw IOException("Mask frame exceeds $MAX_LINE_BYTES bytes")
    socket.getOutputStream().write(frame)
    socket.getOutputStream().flush()
    lastSentMask = mask
  }

  private fun startReader() {
    Thread({
      val buffer = ByteArray(512)
      try {
        val input = socket.getInputStream()
        while (!closed.get()) {
          if (input.read(buffer) < 0) {
            if (closed.compareAndSet(false, true)) {
              onPeerLost("USB host closed the TCP connection")
            }
            return@Thread
          }
        }
      } catch (error: IOException) {
        if (closed.compareAndSet(false, true)) {
          onPeerLost("USB TCP connection ended: ${error.message ?: "socket error"}")
        }
      }
    }, "JoJoUsbReader").apply {
      isDaemon = true
      start()
    }
  }

  companion object {
    private const val WATCHDOG_MS = 300L
    private const val CONNECT_TIMEOUT_MS = 5_000
    private const val HANDSHAKE_TIMEOUT_MS = 3_000
    private const val MAX_LINE_BYTES = 256
    private val TOKEN_PATTERN = Regex("^[0-9a-f]{32}$")

    /** Connect and complete the bounded version-1 NDJSON handshake before returning a socket. */
    @Throws(IOException::class)
    fun connectAndHandshake(token: String, socket: Socket): Socket {
      try {
        require(TOKEN_PATTERN.matches(token)) { "USB token must be 32 lowercase hexadecimal characters" }
        socket.tcpNoDelay = true
        socket.connect(InetSocketAddress("127.0.0.1", 8765), CONNECT_TIMEOUT_MS)
        socket.soTimeout = HANDSHAKE_TIMEOUT_MS
        val hello = JSONObject().put("token", token).put("protocol", 1)
          .toString().toByteArray(StandardCharsets.UTF_8) + byteArrayOf('\n'.code.toByte())
        if (hello.size > MAX_LINE_BYTES) throw IOException("USB handshake exceeds $MAX_LINE_BYTES bytes")
        socket.getOutputStream().write(hello)
        socket.getOutputStream().flush()

        val line = readBoundedLine(socket)
        val ack = try {
          JSONObject(String(line, StandardCharsets.UTF_8))
        } catch (error: Exception) {
          throw IOException("Invalid USB handshake acknowledgement", error)
        }
        if (!ack.optBoolean("ok", false) || ack.optInt("protocol", -1) != 1) {
          throw IOException("USB host rejected protocol 1 handshake")
        }
        socket.soTimeout = 0
        return socket
      } catch (error: Throwable) {
        try { socket.close() } catch (_: IOException) {}
        throw error
      }
    }

    @Throws(IOException::class)
    private fun readBoundedLine(socket: Socket): ByteArray {
      val bytes = ByteArrayOutputStream()
      val input = socket.getInputStream()
      while (true) {
        val value = input.read()
        if (value < 0) throw EOFException("USB host closed before handshake acknowledgement")
        if (value == '\n'.code) return bytes.toByteArray()
        if (bytes.size() >= MAX_LINE_BYTES - 1) throw IOException("USB acknowledgement exceeds $MAX_LINE_BYTES bytes")
        bytes.write(value)
      }
    }
  }
}
