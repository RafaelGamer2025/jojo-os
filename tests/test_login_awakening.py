from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from core import login_in_window
from core.login_in_window import LoginWindow


class FakeEntry:
    def __init__(self, value: str):
        self.value = value

    def get(self) -> str:
        return self.value


class AwakeningAccountTests(unittest.TestCase):
    def test_registration_saves_stand_and_cleiton_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            dialog = LoginWindow.__new__(LoginWindow)
            dialog.db_file = Path(directory) / "users.db"
            dialog.pending_profile = "CLEITON"
            dialog.win = Mock()
            dialog.setup_login_ui = Mock()
            stored = {}

            with (
                patch.object(login_in_window, "carregar_db_seguro", return_value={}),
                patch.object(login_in_window, "salvar_db_seguro", side_effect=lambda db, _path: stored.update(db)),
                patch.object(login_in_window.messagebox, "showinfo"),
            ):
                dialog._salvar_nova_conta(
                    "rafe",
                    "SenhaForte123!",
                    "Silver Chariot",
                    {"bg": "#080610", "fg": "#B8C2D1", "accent": "#B8C2D1"},
                    "user",
                )

            self.assertEqual(stored["rafe"]["stand"], "Silver Chariot")
            self.assertEqual(stored["rafe"]["os_profile"], "CLEITON")
            self.assertEqual(stored["rafe"]["role"], "user")
            dialog.setup_login_ui.assert_called_once_with()

    def test_login_passes_awakened_stand_and_profile_to_desktop(self):
        account = {
            "password": "hashed",
            "role": "user",
            "stand": "The Sun",
            "theme_data": {"bg": "#080610", "fg": "#F2A52B", "accent": "#F2A52B"},
            "os_profile": "CLEITON",
        }
        dialog = LoginWindow.__new__(LoginWindow)
        dialog.db_file = Path("unused.db")
        dialog.ent_user = FakeEntry("rafe")
        dialog.ent_pass = FakeEntry("senha")
        dialog.win = Mock()
        dialog.on_success = Mock()

        with (
            patch.object(login_in_window, "carregar_db_seguro", return_value={"rafe": account}),
            patch.object(login_in_window, "verificar_senha", return_value=(True, False)),
        ):
            dialog.check_login()

        dialog.win.destroy.assert_called_once_with()
        dialog.on_success.assert_called_once_with(
            "rafe",
            is_admin=False,
            theme_data=account["theme_data"],
            stand="The Sun",
            os_profile="CLEITON",
        )

    def test_legacy_accounts_default_to_jojo_profile_and_no_stand(self):
        account = {"password": "hashed", "role": "user"}
        dialog = LoginWindow.__new__(LoginWindow)
        dialog.db_file = Path("unused.db")
        dialog.ent_user = FakeEntry("legacy")
        dialog.ent_pass = FakeEntry("senha")
        dialog.win = Mock()
        dialog.on_success = Mock()

        with (
            patch.object(login_in_window, "carregar_db_seguro", return_value={"legacy": account}),
            patch.object(login_in_window, "verificar_senha", return_value=(True, False)),
        ):
            dialog.check_login()

        dialog.on_success.assert_called_once_with(
            "legacy",
            is_admin=False,
            theme_data=None,
            stand=None,
            os_profile="JOJO",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
