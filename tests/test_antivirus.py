from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from core.antivirus import (
    EngineInfo,
    _defender_status,
    build_scan_command,
    classify_scan_output,
    detect_engine,
    find_defender_cli,
)


class AntivirusAdapterTests(unittest.TestCase):
    def test_defender_command_uses_argument_list_and_disables_remediation(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "sample file.txt"
            target.write_text("benign test data", encoding="utf-8")
            engine = EngineInfo(
                engine_id="defender",
                name="Microsoft Defender Antivirus",
                available=True,
                executable=r"C:\Program Files\Windows Defender\MpCmdRun.exe",
                detail="test",
            )
            command = build_scan_command(engine, target)
            self.assertEqual(command[-3:], ["-File", str(target.resolve()), "-DisableRemediation"])
            self.assertIn("-ScanType", command)
            self.assertNotIn("-Remove", command)
            self.assertNotIn("-Restore", command)

    def test_clamav_command_is_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "safe"
            target.mkdir()
            engine = EngineInfo("clamav", "ClamAV", True, "/usr/bin/clamscan", "test")
            command = build_scan_command(engine, target)
            self.assertEqual(command, ["/usr/bin/clamscan", "--recursive", "--infected", str(target.resolve())])
            self.assertNotIn("--remove", command)
            self.assertNotIn("--move", command)

    def test_clamav_result_codes_are_not_confused(self):
        self.assertEqual(
            classify_scan_output("clamav", 0, ["SCAN SUMMARY", "Infected files: 0"])[0],
            "clean",
        )
        verdict, detections, _ = classify_scan_output(
            "clamav", 1, ["/tmp/EICAR.txt: Win.Test.EICAR FOUND"]
        )
        self.assertEqual((verdict, detections), ("detections", 1))
        self.assertEqual(classify_scan_output("clamav", 2, ["permission denied"])[0], "error")

    def test_defender_exit_code_two_is_not_reported_clean(self):
        verdict, count, _ = classify_scan_output("defender", 2, ["Access denied"])
        self.assertEqual((verdict, count), ("inconclusive", 0))
        self.assertEqual(classify_scan_output("defender", 0, ["No threats found"])[0], "clean")
        self.assertEqual(
            classify_scan_output("defender", 0, ["ThreatName: Test.Malware"])[0],
            "detections",
        )

    def test_defender_locator_uses_highest_platform_version(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            platform_root = root / "Microsoft" / "Windows Defender" / "Platform"
            older = platform_root / "4.18.1.0"
            newer = platform_root / "4.18.20.0"
            older.mkdir(parents=True)
            newer.mkdir(parents=True)
            (older / "MpCmdRun.exe").write_bytes(b"test")
            (newer / "MpCmdRun.exe").write_bytes(b"test")
            path = find_defender_cli(
                {"ProgramData": directory, "ProgramFiles": directory},
                which=lambda _name: None,
            )
            self.assertEqual(path, str(newer / "MpCmdRun.exe"))

    def test_defender_status_is_read_with_fixed_powershell_script(self):
        payload = {
            "service_enabled": True,
            "antivirus_enabled": True,
            "real_time_enabled": True,
            "engine_version": "1.2.3",
            "signature_version": "4.5.6",
        }

        def fake_run(command, **kwargs):
            self.assertIn("Get-MpComputerStatus", command[-1])
            self.assertEqual(kwargs["timeout"], 20)
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload), stderr="")

        engine, signatures, real_time, detail = _defender_status("powershell.exe", fake_run)
        self.assertEqual((engine, signatures, real_time), ("1.2.3", "4.5.6", True))
        self.assertIn("proteção ativa", detail)

    def test_missing_scanner_is_reported_as_unavailable(self):
        engine = detect_engine("Linux", which=lambda _name: None)
        self.assertFalse(engine.available)
        self.assertEqual(engine.engine_id, "none")
        self.assertIn("ClamAV não está instalado", engine.detail)


if __name__ == "__main__":
    unittest.main(verbosity=2)
