from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core import database
from core.app_catalog import (
    OPTIONAL_APP_ID,
    OPTIONAL_APPS_SETTING_KEY,
    get_installed_optional_apps,
    install_optional_app,
    uninstall_optional_app,
)


class AppCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "jojo_os.db"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_default_is_not_installed(self) -> None:
        self.assertEqual(get_installed_optional_apps(path=self.db_path), set())
        self.assertIsNone(
            database.get_setting(OPTIONAL_APPS_SETTING_KEY, None, path=self.db_path)
        )

    def test_installation_and_idempotence(self) -> None:
        self.assertEqual(
            install_optional_app(OPTIONAL_APP_ID, path=self.db_path),
            {OPTIONAL_APP_ID},
        )
        self.assertEqual(
            get_installed_optional_apps(path=self.db_path), {OPTIONAL_APP_ID}
        )
        self.assertEqual(
            install_optional_app(OPTIONAL_APP_ID, path=self.db_path),
            {OPTIONAL_APP_ID},
        )
        self.assertEqual(
            database.get_setting(OPTIONAL_APPS_SETTING_KEY, path=self.db_path),
            [OPTIONAL_APP_ID],
        )

    def test_uninstallation_preserves_other_settings(self) -> None:
        database.set_setting("tema_atual", {"nome": "JOJO"}, path=self.db_path)
        install_optional_app(OPTIONAL_APP_ID, path=self.db_path)

        self.assertEqual(uninstall_optional_app(OPTIONAL_APP_ID, path=self.db_path), set())
        self.assertEqual(get_installed_optional_apps(path=self.db_path), set())
        self.assertEqual(
            database.get_setting("tema_atual", path=self.db_path), {"nome": "JOJO"}
        )
        self.assertEqual(
            database.get_setting(OPTIONAL_APPS_SETTING_KEY, path=self.db_path), []
        )
        self.assertEqual(uninstall_optional_app(OPTIONAL_APP_ID, path=self.db_path), set())

    def test_unknown_ids_are_rejected(self) -> None:
        unknown_id = "app_inexistente"
        with self.assertRaises(ValueError):
            install_optional_app(unknown_id, path=self.db_path)
        with self.assertRaises(ValueError):
            uninstall_optional_app(unknown_id, path=self.db_path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
