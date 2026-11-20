"""Dependency-free static checks for the local Expo module's shipping contract."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ModuleContractTests(unittest.TestCase):
    def test_expo_local_registration_is_android_only(self):
        config = json.loads((ROOT / "expo-module.config.json").read_text())
        self.assertEqual(config["platforms"], ["android"])
        self.assertEqual(
            config["android"]["modules"],
            ["expo.modules.jojocontroller.JoJoControllerModule"],
        )
        package = json.loads((ROOT / "package.json").read_text())
        self.assertEqual(package["name"], "jojo-controller")

    def test_manifest_permissions_are_scoped_correctly(self):
        manifest = (ROOT / "android/src/main/AndroidManifest.xml").read_text()
        self.assertIn('android:name="android.permission.INTERNET"', manifest)
        self.assertIn('android:name="android.permission.BLUETOOTH_CONNECT"', manifest)
        for permission in ("BLUETOOTH", "BLUETOOTH_ADMIN"):
            self.assertRegex(
                manifest,
                rf'android:name="android.permission.{permission}"[^>]*android:maxSdkVersion="30"',
            )

    def test_native_api_and_usb_wire_contract(self):
        module = (ROOT / "android/src/main/java/expo/modules/jojocontroller/JoJoControllerModule.kt").read_text()
        usb = (ROOT / "android/src/main/java/expo/modules/jojocontroller/UsbTcpSession.kt").read_text()
        for symbol in ('Name("JoJoController")', 'Events("onStatus")', 'AsyncFunction("capabilities")',
                       'AsyncFunction("listBondedDevices")', 'AsyncFunction("startBluetooth")',
                       'AsyncFunction("connectUsb")', 'Function("setMask")', 'AsyncFunction("disconnect")',
                       'AsyncFunction("openBluetoothSettings")'):
            self.assertIn(symbol, module)
        self.assertIn('InetSocketAddress("127.0.0.1", 8765)', usb)
        self.assertIn('put("protocol", 1)', usb)
        self.assertIn('"{\\"mask\\":$mask}\\n"', usb)
        self.assertIn('WATCHDOG_MS = 300L', usb)
        self.assertRegex(usb, r'if \(lastSentMask != 0\) sendMask\(0\)')
        self.assertIn('input.read(buffer) < 0', usb)

    def test_report_mask_limits_and_hid_descriptor(self):
        report = (ROOT / "android/src/main/java/expo/modules/jojocontroller/JoJoGamepadReport.kt").read_text()
        self.assertIn('const val MASK_MAX: Int = 2047', report)
        self.assertIn('val buttons = (mask ushr 4) and 0x7F', report)
        self.assertIn('else -> 8 // centered, or opposing direction bits', report)
        self.assertIn('0x09, 0x05', report)  # Generic Desktop Game Pad
        self.assertTrue((ROOT / "android/src/test/java/expo/modules/jojocontroller/JoJoGamepadReportTest.kt").is_file())

    def test_usb_state_updates_do_not_load_hid_on_older_android(self):
        module = (ROOT / "android/src/main/java/expo/modules/jojocontroller/JoJoControllerModule.kt").read_text()
        section = module.split('Function("setMask")', 1)[1].split('AsyncFunction("disconnect")', 1)[0]
        self.assertIn('if (Build.VERSION.SDK_INT >= 28 && mode == "bluetooth")', section)
        self.assertLess(section.index('if (Build.VERSION.SDK_INT >= 28'), section.index('bluetooth.onMaskRefreshed()'))

    def test_set_mask_return_matches_void_typescript_contract(self):
        module = (ROOT / "android/src/main/java/expo/modules/jojocontroller/JoJoControllerModule.kt").read_text()
        section = module.split('Function("setMask")', 1)[1].split('AsyncFunction("disconnect")', 1)[0]
        self.assertRegex(section, r'\}\s+Unit\s+\}\s*$')
        self.assertIn('setMask(mask: number): void;', (ROOT / "src/index.ts").read_text())


if __name__ == "__main__":
    unittest.main(verbosity=2)
