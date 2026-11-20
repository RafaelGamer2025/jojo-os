package expo.modules.jojocontroller

/** Wire format for the single, report-protocol HID gamepad exposed by this module. */
internal object JoJoGamepadReport {
  const val REPORT_ID: Byte = 1
  const val REPORT_TYPE_INPUT: Byte = 1
  const val MASK_MAX: Int = 2047

  // Seven buttons (A/B/C/X/Y/Z/Start), one hat switch and neutral hat value 8.
  // There are deliberately no keyboard usages or boot-protocol reports.
  val DESCRIPTOR: ByteArray = byteArrayOf(
    0x05, 0x01,             // Usage Page (Generic Desktop)
    0x09, 0x05,             // Usage (Game Pad)
    0xA1.toByte(), 0x01,    // Collection (Application)
    0x85.toByte(), 0x01,    //   Report ID (1)
    0x05, 0x09,             //   Usage Page (Button)
    0x19, 0x01, 0x29, 0x07, //   Usage Minimum (1), Maximum (7)
    0x15, 0x00, 0x25, 0x01, //   Logical Minimum (0), Maximum (1)
    0x95.toByte(), 0x07, 0x75, 0x01, 0x81.toByte(), 0x02,
    0x95.toByte(), 0x01, 0x75, 0x01, 0x81.toByte(), 0x03, // 1 padding bit
    0x05, 0x01, 0x09, 0x39, //   Usage Page (Generic Desktop), Hat Switch
    0x15, 0x00, 0x25, 0x07, //   Logical range 0..7
    0x35, 0x00, 0x46, 0x3B, 0x01, 0x65, 0x14,
    0x75, 0x04, 0x95.toByte(), 0x01, 0x81.toByte(), 0x42, // 4-bit hat, null state
    0x65, 0x00, 0x75, 0x04, 0x95.toByte(), 0x01, 0x81.toByte(), 0x03, // padding
    0xC0.toByte()           // End Collection
  )

  /** Mask bits: 0 Up, 1 Down, 2 Left, 3 Right, 4 A, 5 B, 6 C, 7 X, 8 Y, 9 Z, 10 Start. */
  fun encode(mask: Int): ByteArray {
    require(mask in 0..MASK_MAX) { "Mask must be in 0..$MASK_MAX" }
    val buttons = (mask ushr 4) and 0x7F
    val up = mask and (1 shl 0) != 0
    val down = mask and (1 shl 1) != 0
    val left = mask and (1 shl 2) != 0
    val right = mask and (1 shl 3) != 0
    val vertical = when {
      up && !down -> -1
      down && !up -> 1
      else -> 0
    }
    val horizontal = when {
      right && !left -> 1
      left && !right -> -1
      else -> 0
    }
    val hat = when {
      vertical < 0 && horizontal > 0 -> 1 // up-right
      vertical > 0 && horizontal > 0 -> 3 // down-right
      vertical > 0 && horizontal < 0 -> 5 // down-left
      vertical < 0 && horizontal < 0 -> 7 // up-left
      vertical < 0 -> 0
      horizontal > 0 -> 2
      vertical > 0 -> 4
      horizontal < 0 -> 6
      else -> 8 // centered, or opposing direction bits
    }
    return byteArrayOf(buttons.toByte(), hat.toByte())
  }
}
