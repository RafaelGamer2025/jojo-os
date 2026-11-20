from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import database, security
from core.battle_system import criar_lutador, turno_batalha
from core.safe_math import CalculationError, safe_calculate
from core.workspace import resolve_workspace_path, validate_filename
from ui.theme_manager import Theme


class FixedRng:
    def randint(self, low, high):
        return low

    def random(self):
        return 1.0


class SafeMathTests(unittest.TestCase):
    def test_basic_arithmetic(self):
        self.assertEqual(safe_calculate("2 + 3 * 4"), 14)
        self.assertEqual(safe_calculate("(12 - 4) / 2"), 4)

    def test_rejects_code_and_unsafe_operations(self):
        for expr in ["__import__('os').system('echo bad')", "1 / 0", "2 ** 101", "True", "1 << 3"]:
            with self.subTest(expr=expr), self.assertRaises(CalculationError):
                safe_calculate(expr)


class PasswordTests(unittest.TestCase):
    def test_pbkdf2_and_legacy_sha_migration(self):
        encoded = security.hash_password("Uma senha longa!123")
        self.assertTrue(security.verificar_senha(encoded, "Uma senha longa!123")[0])
        self.assertFalse(security.verificar_senha(encoded, "errada")[0])
        legacy = hashlib.sha256(b"senha antiga").hexdigest()
        self.assertEqual(security.verificar_senha(legacy, "senha antiga"), (True, True))


class SecureStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data = self.root / "data"
        self.data.mkdir()
        self.users = self.data / "users.json"
        self.db_path = self.data / "jojo_os.db"
        self.key_file = self.data / "system_key.json"
        self.key_file.write_text(json.dumps({"key": "short-old-key"}), encoding="utf-8")
        self.patches = [
            patch.object(security, "PROJECT_ROOT", self.root),
            patch.object(security, "DATA_DIR", self.data),
            patch.object(security, "DB_FILE", self.db_path),
            patch.object(security, "LEGACY_DB_FILE", self.users),
            patch.object(security, "SYSTEM_KEY_FILE", self.key_file),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def test_save_rotates_short_key_and_roundtrips(self):
        db = {"demo": {"password": security.hash_password("Test password 123!"), "role": "user"}}
        security.salvar_db_seguro(db, self.db_path)
        self.assertTrue(self.db_path.read_bytes().startswith(b"SQLite format 3\x00"))
        self.assertEqual(security.carregar_db_seguro(self.db_path), db)
        key = json.loads(self.key_file.read_text(encoding="utf-8"))["key"]
        self.assertGreaterEqual(len(key), 32)

    def test_reads_valid_nested_legacy_envelope(self):
        key = "legacy"
        self.key_file.write_text(json.dumps({"key": key}), encoding="utf-8")
        users = {"demo": {"password": hashlib.sha256(b"senha").hexdigest(), "role": "user"}}

        def old_signature(payload):
            return hashlib.sha256((json.dumps(payload, sort_keys=True) + key).encode()).hexdigest()

        inner = {"data": users, "assinatura": old_signature(users)}
        outer = {"data": inner, "assinatura": old_signature(inner)}
        self.users.write_text(json.dumps(outer), encoding="utf-8")
        self.assertEqual(security.carregar_db_seguro(self.db_path), users)
        self.assertTrue(self.db_path.is_file())
        self.assertFalse(self.users.exists())
        self.assertTrue((self.data / "users.json.migrated.bak").is_file())
        self.assertEqual(security.carregar_db_seguro(self.db_path), users)

    def test_rejects_bad_signature(self):
        self.users.write_text(json.dumps({"version": 2, "data": {"demo": {}}, "assinatura": "invalid"}), encoding="utf-8")
        loaded = security.carregar_db_seguro(self.db_path)
        self.assertIs(loaded.get("__hack_detected__"), True)
        self.assertFalse(self.db_path.exists())
        self.assertTrue(self.users.exists())

    def test_sqlite_record_tampering_is_detected(self):
        security.salvar_db_seguro({"demo": {"role": "user"}}, self.db_path)
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                "UPDATE users SET record_json = ? WHERE username = 'demo'",
                ('{"role":"admin"}',),
            )
        loaded = security.carregar_db_seguro(self.db_path)
        self.assertIs(loaded.get("__hack_detected__"), True)

    def test_empty_database_is_signed_and_missing_signature_is_detected(self):
        self.assertEqual(security.carregar_db_seguro(self.db_path), {})
        self.assertEqual(security.carregar_db_seguro(self.db_path), {})
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("DELETE FROM app_metadata WHERE key = 'users_hmac'")
        loaded = security.carregar_db_seguro(self.db_path)
        self.assertIs(loaded.get("__hack_detected__"), True)

    def test_database_can_be_rebuilt_from_migration_backup(self):
        key = "short-old-key"
        users = {"demo": {"role": "user"}}

        def old_signature(payload):
            return hashlib.sha256((json.dumps(payload, sort_keys=True) + key).encode()).hexdigest()

        self.users.write_text(
            json.dumps({"data": users, "assinatura": old_signature(users)}),
            encoding="utf-8",
        )
        self.assertEqual(security.carregar_db_seguro(self.db_path), users)
        self.db_path.unlink()
        self.assertEqual(security.carregar_db_seguro(self.db_path), users)


class DatabaseTests(unittest.TestCase):
    def test_settings_and_scan_history_persist_in_sqlite(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "jojo_os.db"
            positions = {"IA": [40, 60], "terminal": [80, 120]}
            database.set_setting("icon_positions", positions, path=db_path)
            self.assertEqual(database.get_setting("icon_positions", {}, path=db_path), positions)

            scan_id = database.record_scan(
                engine="ClamAV",
                target="/tmp/sample.txt",
                verdict="clean",
                detections=0,
                summary="Nenhuma detecção informada pelo ClamAV.",
                started_at="2026-11-01T12:00:00+00:00",
                finished_at="2026-11-01T12:00:01+00:00",
                exit_code=0,
                path=db_path,
            )
            history = database.list_scan_history(path=db_path)
            self.assertEqual(history[0]["id"], scan_id)
            self.assertEqual(history[0]["target"], "/tmp/sample.txt")
            database.clear_scan_history(db_path)
            self.assertEqual(database.list_scan_history(path=db_path), [])
            database.set_setting("system_state", {"ready": True}, path=db_path)
            database.delete_setting("system_state", path=db_path)
            self.assertIsNone(database.get_setting("system_state", None, path=db_path))


class WorkspaceTests(unittest.TestCase):
    def test_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "workspace"
            root.mkdir()
            self.assertEqual(resolve_workspace_path(root, "file.txt"), root / "file.txt")
            with self.assertRaises(ValueError):
                resolve_workspace_path(root, "../../outside.txt")

    def test_filename_validation(self):
        self.assertEqual(validate_filename("notes.txt"), "notes.txt")
        for name in ["../escape.txt", "CON", "", "trailing."]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_filename(name)


class BattleTests(unittest.TestCase):
    def test_health_is_clamped_at_zero_and_defeated_target_does_not_retaliate(self):
        player = criar_lutador("Star Platinum")
        enemy = criar_lutador("The World")
        enemy["hp"] = 1
        messages = turno_batalha(player, enemy, rng=FixedRng())
        self.assertEqual(enemy["hp"], 0)
        self.assertEqual(player["hp"], 100)
        self.assertTrue(any("derrotado" in message for message in messages))

    def test_unknown_stand_is_rejected(self):
        with self.assertRaises(ValueError):
            criar_lutador("Unknown Stand")


class ThemeTests(unittest.TestCase):
    def test_theme_colors_are_copied_per_instance(self):
        jojo = Theme("JOJO")
        hacker = Theme("HACKER")
        colors = jojo.current
        colors["bg"] = "#123456"
        self.assertNotEqual(jojo.current["bg"], "#123456")
        self.assertEqual(hacker.current["bg"], "#0D0208")


if __name__ == "__main__":
    unittest.main(verbosity=2)
