from __future__ import annotations

import json
import socket
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from core.games import controller_bridge as bridge_module
from core.games.controller_bridge import (
    DEFAULT_MAPPING,
    AdbReverseLease,
    ControllerBridge,
    ControllerState,
    RecordingKeyboardBackend,
    establish_adb_reverse,
    find_adb_path,
    neutralize_opposites,
    validate_mapping,
)


def wait_for(predicate, timeout: float = 1.5) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return bool(predicate())


def send_json_line(connection: socket.socket, value: dict[str, object]) -> None:
    connection.sendall(json.dumps(value, separators=(",", ":")).encode() + b"\n")


def recv_line(connection: socket.socket) -> bytes:
    data = bytearray()
    while not data.endswith(b"\n"):
        chunk = connection.recv(1)
        if not chunk:
            break
        data.extend(chunk)
    return bytes(data)


class ControllerBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = RecordingKeyboardBackend()
        self.statuses: list[str] = []
        self.bridge = ControllerBridge(
            backend=self.backend,
            port=0,
            on_status=self.statuses.append,
        )
        self.token = self.bridge.start()

    def tearDown(self) -> None:
        self.bridge.stop()

    def connect_authenticated(self) -> socket.socket:
        client = socket.create_connection(("127.0.0.1", self.bridge.port), timeout=1)
        client.settimeout(1)
        send_json_line(client, {"token": self.token, "protocol": 1})
        self.assertEqual(recv_line(client), b'{"ok":true,"protocol":1}\n')
        return client

    def test_token_is_random_32_lower_hex_and_listener_is_loopback(self) -> None:
        self.assertRegex(self.token, r"^[0-9a-f]{32}$")
        assert self.bridge._listener is not None
        self.assertEqual(self.bridge._listener.getsockname()[0], "127.0.0.1")
        other = ControllerBridge(backend=RecordingKeyboardBackend(), port=0)
        try:
            other_token = other.start()
            self.assertRegex(other_token, r"^[0-9a-f]{32}$")
            self.assertNotEqual(self.token, other_token)
        finally:
            other.stop()

    def test_handshake_ack_once_and_masks_have_no_ack(self) -> None:
        with self.connect_authenticated() as client:
            send_json_line(client, {"mask": 0})
            self.assertTrue(wait_for(lambda: not self.bridge._state.needs_neutral))
            send_json_line(client, {"mask": 1 << 4})
            self.assertTrue(wait_for(lambda: self.backend.current_keys == {"z"}))
            client.settimeout(0.15)
            with self.assertRaises(socket.timeout):
                client.recv(1)

    def test_opposite_directions_are_neutralized(self) -> None:
        with self.connect_authenticated() as client:
            send_json_line(client, {"mask": 0})
            self.assertTrue(wait_for(lambda: not self.bridge._state.needs_neutral))
            send_json_line(client, {"mask": (1 << 0) | (1 << 1) | (1 << 4)})
            self.assertTrue(wait_for(lambda: self.backend.current_keys == {"z"}))
            self.assertEqual(neutralize_opposites(0b1111), 0)

    def test_bad_token_disconnects_and_releases_keys(self) -> None:
        with self.connect_authenticated() as client:
            send_json_line(client, {"mask": 0})
            self.assertTrue(wait_for(lambda: not self.bridge._state.needs_neutral))
            send_json_line(client, {"mask": 1 << 4})
            self.assertTrue(wait_for(lambda: self.backend.current_keys == {"z"}))

        bad = socket.create_connection(("127.0.0.1", self.bridge.port), timeout=1)
        bad.settimeout(1)
        send_json_line(bad, {"token": "0" * 32, "protocol": 1})
        self.assertTrue(wait_for(lambda: self.backend.current_keys == set()))
        self.assertTrue(wait_for(lambda: any("Token ou versão" in text for text in self.statuses)))
        bad.close()

    def test_malformed_mask_releases_and_disconnects(self) -> None:
        client = self.connect_authenticated()
        send_json_line(client, {"mask": 0})
        self.assertTrue(wait_for(lambda: not self.bridge._state.needs_neutral))
        send_json_line(client, {"mask": 1 << 4})
        self.assertTrue(wait_for(lambda: self.backend.current_keys == {"z"}))
        client.sendall(b'{"mask":true}\n')
        self.assertTrue(wait_for(lambda: self.backend.current_keys == set()))
        self.assertTrue(wait_for(lambda: any("inteiro entre 0 e 2047" in text for text in self.statuses)))
        client.close()

    def test_oversized_line_is_rejected_and_keys_released(self) -> None:
        client = self.connect_authenticated()
        send_json_line(client, {"mask": 0})
        self.assertTrue(wait_for(lambda: not self.bridge._state.needs_neutral))
        send_json_line(client, {"mask": 1 << 4})
        self.assertTrue(wait_for(lambda: self.backend.current_keys == {"z"}))
        client.sendall(b" " * 257 + b"\n")
        self.assertTrue(wait_for(lambda: self.backend.current_keys == set()))
        self.assertTrue(wait_for(lambda: any("256 bytes" in text for text in self.statuses)))
        client.close()

    def test_client_inactivity_timeout_releases_keys(self) -> None:
        client = self.connect_authenticated()
        send_json_line(client, {"mask": 0})
        self.assertTrue(wait_for(lambda: not self.bridge._state.needs_neutral))
        send_json_line(client, {"mask": 1 << 4})
        self.assertTrue(wait_for(lambda: self.backend.current_keys == {"z"}))
        self.assertTrue(wait_for(lambda: self.backend.current_keys == set(), timeout=1.2))
        self.assertTrue(wait_for(lambda: any("0,5 segundo" in text for text in self.statuses)))
        client.close()

    def test_second_concurrent_client_is_rejected(self) -> None:
        first = socket.create_connection(("127.0.0.1", self.bridge.port), timeout=1)
        second = socket.create_connection(("127.0.0.1", self.bridge.port), timeout=1)
        second.settimeout(1)
        self.assertEqual(second.recv(1), b"")
        first.settimeout(1)
        send_json_line(first, {"token": self.token, "protocol": 1})
        self.assertEqual(recv_line(first), b'{"ok":true,"protocol":1}\n')
        first.close()
        second.close()

    def test_wrong_protocol_and_extra_handshake_fields_are_rejected(self) -> None:
        client = socket.create_connection(("127.0.0.1", self.bridge.port), timeout=1)
        client.settimeout(1)
        send_json_line(
            client,
            {"token": self.token, "protocol": 1, "shell": "must-not-be-run"},
        )
        self.assertTrue(wait_for(lambda: any("campos inválidos" in text for text in self.statuses)))
        client.close()

    def test_stop_releases_keys_and_is_deterministic(self) -> None:
        client = self.connect_authenticated()
        send_json_line(client, {"mask": 0})
        self.assertTrue(wait_for(lambda: not self.bridge._state.needs_neutral))
        send_json_line(client, {"mask": 1 << 4})
        self.assertTrue(wait_for(lambda: self.backend.current_keys == {"z"}))
        self.bridge.stop()
        self.assertEqual(self.backend.current_keys, set())
        self.bridge.stop()
        client.close()


class ControllerStateTests(unittest.TestCase):
    def test_focus_regain_requires_a_fresh_neutral_mask(self) -> None:
        backend = RecordingKeyboardBackend()
        focused = [True]
        state = ControllerState(backend, focus_check=lambda: focused[0])

        state.apply_mask(0)
        state.apply_mask(1 << 4)
        self.assertEqual(backend.current_keys, {"z"})

        focused[0] = False
        state.tick_focus()
        self.assertEqual(backend.current_keys, set())
        focused[0] = True
        state.tick_focus()
        state.apply_mask(1 << 4)
        self.assertEqual(backend.current_keys, set())
        self.assertTrue(state.needs_neutral)

        state.apply_mask(0)
        self.assertFalse(state.needs_neutral)
        state.apply_mask(1 << 4)
        self.assertEqual(backend.current_keys, {"z"})

    def test_focus_check_exception_fails_closed(self) -> None:
        backend = RecordingKeyboardBackend()
        state = ControllerState(backend, focus_check=lambda: (_ for _ in ()).throw(OSError()))
        state.apply_mask(0)
        state.apply_mask(1 << 4)
        self.assertEqual(backend.current_keys, set())
        self.assertTrue(state.needs_neutral)

    def test_mapping_is_fixed_unique_and_restricted(self) -> None:
        self.assertEqual(validate_mapping(DEFAULT_MAPPING), DEFAULT_MAPPING)
        duplicate = dict(DEFAULT_MAPPING)
        duplicate["B"] = duplicate["A"]
        with self.assertRaisesRegex(ValueError, "diferente"):
            validate_mapping(duplicate)
        invalid = dict(DEFAULT_MAPPING)
        invalid["Start"] = "escape"
        with self.assertRaisesRegex(ValueError, "não permitida"):
            validate_mapping(invalid)
        with self.assertRaisesRegex(ValueError, "11 controles"):
            validate_mapping({"A": "z"})
        with self.assertRaisesRegex(ValueError, "11 controles"):
            ControllerState(RecordingKeyboardBackend(), mapping={})
        with self.assertRaisesRegex(ValueError, "11 controles"):
            ControllerBridge(backend=RecordingKeyboardBackend(), mapping={})

    def test_mask_range_rejects_bool_and_out_of_range(self) -> None:
        for value in (True, -1, 2048, "1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                neutralize_opposites(value)  # type: ignore[arg-type]


class AdbTests(unittest.TestCase):
    def test_explicit_project_and_path_adb_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            chosen = root / "custom-adb.exe"
            chosen.touch()
            bundled = root / "tools" / "platform-tools" / "adb.exe"
            bundled.parent.mkdir(parents=True)
            bundled.touch()
            self.assertEqual(find_adb_path(chosen), str(chosen.resolve()))
            self.assertEqual(find_adb_path(root=root), str(bundled.resolve()))
            with patch.object(bridge_module.shutil, "which", return_value="/usr/bin/adb"):
                self.assertEqual(find_adb_path(root=root / "empty"), "/usr/bin/adb")
            with self.assertRaises(FileNotFoundError):
                find_adb_path(root=root / "empty")

    def test_unexpected_adb_reverse_is_not_run_for_unauthorized_phone(self) -> None:
        devices = subprocess.CompletedProcess(
            args=["adb", "devices", "-l"],
            returncode=0,
            stdout="List of devices attached\nABC unauthorized usb:1-2\n",
        )
        with (
            patch.object(bridge_module, "_run_adb", return_value=devices) as run_adb,
            self.assertRaisesRegex(RuntimeError, "aceite a permissão"),
        ):
            establish_adb_reverse("adb")
        run_adb.assert_called_once_with("adb", ["devices", "-l"])

    def test_authorized_phone_uses_exact_reverse_command_and_owned_cleanup(self) -> None:
        outputs = [
            subprocess.CompletedProcess(
                args=["adb", "devices", "-l"],
                returncode=0,
                stdout="List of devices attached\nABC device usb:1-2 product:phone\n",
            ),
            subprocess.CompletedProcess(args=["adb", "reverse"], returncode=0, stdout=""),
            subprocess.CompletedProcess(args=["adb", "reverse", "--remove"], returncode=0, stdout=""),
        ]
        with patch.object(bridge_module, "_run_adb", side_effect=outputs) as run_adb:
            lease, diagnostics = establish_adb_reverse("adb")
            self.assertTrue(lease.owns_reverse)
            self.assertIn("ABC device", diagnostics)
            self.assertIsNone(lease.cleanup())
            self.assertFalse(lease.owns_reverse)
            self.assertIsNone(lease.cleanup())

        calls = [call.args for call in run_adb.call_args_list]
        self.assertEqual(calls[0], ("adb", ["devices", "-l"]))
        self.assertEqual(
            calls[1],
            ("adb", ["-d", "reverse", "--no-rebind", "tcp:8765", "tcp:8765"]),
        )
        self.assertEqual(calls[2], ("adb", ["-d", "reverse", "--remove", "tcp:8765"]))
        self.assertEqual(run_adb.call_count, 3)

    def test_lease_without_owned_mapping_does_not_remove_anything(self) -> None:
        lease = AdbReverseLease("adb")
        with patch.object(bridge_module, "_run_adb") as run_adb:
            self.assertIsNone(lease.cleanup())
        run_adb.assert_not_called()

    def test_failed_cleanup_keeps_ownership_for_retry(self) -> None:
        lease = AdbReverseLease("adb")
        lease.owns_reverse = True
        outputs = [
            subprocess.CompletedProcess(args=["adb", "reverse"], returncode=1, stdout="busy"),
            subprocess.CompletedProcess(args=["adb", "reverse"], returncode=0, stdout=""),
        ]
        with patch.object(bridge_module, "_run_adb", side_effect=outputs) as run_adb:
            self.assertIn("busy", lease.cleanup() or "")
            self.assertTrue(lease.owns_reverse)
            self.assertIsNone(lease.cleanup())
            self.assertFalse(lease.owns_reverse)
        self.assertEqual(run_adb.call_count, 2)

    def test_reverse_command_uses_no_rebind_and_preserves_existing_mapping(self) -> None:
        outputs = [
            subprocess.CompletedProcess(
                args=["adb", "devices", "-l"],
                returncode=0,
                stdout="List of devices attached\nABC device usb:1-2\n",
            ),
            subprocess.CompletedProcess(
                args=["adb", "reverse"],
                returncode=1,
                stdout="tcp:8765 already in use",
            ),
        ]
        with (
            patch.object(bridge_module, "_run_adb", side_effect=outputs) as run_adb,
            self.assertRaisesRegex(RuntimeError, "não foi substituído"),
        ):
            establish_adb_reverse("adb")
        self.assertEqual(run_adb.call_count, 2)
        self.assertIn("--no-rebind", run_adb.call_args.args[1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
