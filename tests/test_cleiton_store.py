from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.cleiton_store import (
    CLEITON_APP_IDS,
    CLEITON_APPS,
    get_installed_cleiton_apps,
    install_cleiton_app,
    is_cleiton_profile,
    uninstall_cleiton_app,
    visible_cleiton_app_ids,
)
from core.cleiton_tools import execute_cleiton_tool


class CleitonStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "jojo_os.db"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_store_contains_exactly_twenty_unique_apps(self) -> None:
        self.assertEqual(len(CLEITON_APPS), 20)
        self.assertEqual(len(CLEITON_APP_IDS), 20)
        self.assertEqual(len({app.app_id for app in CLEITON_APPS}), 20)

    def test_installation_is_persistent_idempotent_and_whitelisted(self) -> None:
        app_id = CLEITON_APPS[0].app_id
        self.assertEqual(install_cleiton_app(app_id, self.db_path), {app_id})
        self.assertEqual(install_cleiton_app(app_id, self.db_path), {app_id})
        self.assertEqual(get_installed_cleiton_apps(self.db_path), {app_id})
        self.assertEqual(uninstall_cleiton_app(app_id, self.db_path), set())
        with self.assertRaises(ValueError):
            install_cleiton_app("../../arbitrary", self.db_path)

    def test_cleiton_apps_are_invisible_outside_cleiton_profile(self) -> None:
        installed = {CLEITON_APPS[0].app_id, "unknown_old_id"}
        self.assertTrue(is_cleiton_profile("CLEITON"))
        self.assertFalse(is_cleiton_profile("JOJO"))
        self.assertEqual(visible_cleiton_app_ids("JOJO", installed), set())
        self.assertEqual(visible_cleiton_app_ids("HACKER", installed), set())
        self.assertEqual(visible_cleiton_app_ids("CLEITON", installed), {CLEITON_APPS[0].app_id})

    def test_twenty_tools_have_local_functionality(self) -> None:
        payloads = {
            "cleiton_system_info": "",
            "cleiton_processes": "",
            "cleiton_notes": "nota de teste",
            "cleiton_checklist": "tarefa 1",
            "cleiton_unit_converter": "10 km -> mi",
            "cleiton_password_generator": "16",
            "cleiton_sha256": "",
            "cleiton_storage": "",
            "cleiton_network": "",
            "cleiton_json_formatter": '{"ok":true}',
            "cleiton_base64": "encode\nJoJo",
            "cleiton_text_stats": "duas palavras",
            "cleiton_calendar": "2026-11",
            "cleiton_color_converter": "#26A69A",
            "cleiton_percentage": "250, 12.5",
            "cleiton_line_filter": "erro*\nerro um\nok\nerro dois",
            "cleiton_timestamp": "0",
            "cleiton_csv_analyzer": "nome,valor\na,1\nb,2",
            "cleiton_url_codec": "encode\nhello world",
            "cleiton_uuid": "2",
        }
        self.assertEqual(set(payloads), CLEITON_APP_IDS)
        hash_target = Path(self.temp_dir.name) / "tool-smoke.txt"
        hash_target.write_text("smoke", encoding="utf-8")
        for app_id, payload in payloads.items():
            with self.subTest(app_id=app_id):
                result = execute_cleiton_tool(
                    app_id,
                    payload,
                    file_path=hash_target if app_id == "cleiton_sha256" else None,
                    database_path=self.db_path,
                )
                self.assertIsInstance(result, str)
                self.assertTrue(result)

    def test_tools_reject_unknown_ids_and_invalid_payloads(self) -> None:
        with self.assertRaises(ValueError):
            execute_cleiton_tool("unknown_tool")
        with self.assertRaises(ValueError):
            execute_cleiton_tool("cleiton_json_formatter", "not-json")
        with self.assertRaises(ValueError):
            execute_cleiton_tool("cleiton_password_generator", "2")
        with self.assertRaises(ValueError):
            execute_cleiton_tool("cleiton_unit_converter", "10 parsecs -> bananas")
        with self.assertRaises(ValueError):
            execute_cleiton_tool("cleiton_percentage", "nan, 12")

    def test_file_hash_is_sha256_of_chosen_regular_file(self) -> None:
        path = Path(self.temp_dir.name) / "sample.txt"
        path.write_text("abc", encoding="utf-8")
        result = execute_cleiton_tool("cleiton_sha256", file_path=path)
        self.assertIn("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
