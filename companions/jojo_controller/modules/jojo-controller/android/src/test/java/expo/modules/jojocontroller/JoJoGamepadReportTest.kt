package expo.modules.jojocontroller

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class JoJoGamepadReportTest {
  @Test
  fun buttonsUseTheSpecifiedMaskBits() {
    // A=bit 4, B=5, C=6, X=7, Y=8, Z=9, Start=10.
    assertArrayEquals(byteArrayOf(0x7F, 8), JoJoGamepadReport.encode(0x7F shl 4))
    assertArrayEquals(byteArrayOf(0x41, 8), JoJoGamepadReport.encode((1 shl 4) or (1 shl 10)))
  }

  @Test
  fun directionsMapToEightHatSectorsAndNeutral() {
    val expected = listOf(
      0 to 8, 1 to 0, 2 to 4, 3 to 8,
      4 to 6, 5 to 7, 6 to 5, 7 to 6,
      8 to 2, 9 to 1, 10 to 3, 11 to 2,
      12 to 8, 13 to 0, 14 to 4, 15 to 8
    )
    expected.forEach { (directionMask, hat) ->
      assertEquals("mask $directionMask", hat.toByte(), JoJoGamepadReport.encode(directionMask)[1])
    }
  }

  @Test(expected = IllegalArgumentException::class)
  fun rejectsMasksOutsideElevenBits() {
    JoJoGamepadReport.encode(2048)
  }

  @Test
  fun descriptorDeclaresGamepadAndSingleInputReport() {
    val descriptor = JoJoGamepadReport.DESCRIPTOR.map { it.toInt() and 0xFF }
    assertEquals(1, descriptor[1]) // Generic Desktop page
    assertEquals(5, descriptor[3]) // Game Pad usage
    assertEquals(0x85, descriptor[6]) // Report ID item
    assertEquals(1, descriptor[7])
    assertTrue(descriptor.windowed(2).any { it == listOf(0x09, 0x39) }) // Hat-switch usage
  }
}
