from __future__ import annotations

import importlib
import tkinter as tk
import unittest

import pygame


class ImportSafetyTests(unittest.TestCase):
    def setUp(self):
        pygame.quit()

    def test_main_pygame_game_import_does_not_initialize_sdl(self):
        importlib.import_module("games.main")
        self.assertFalse(pygame.get_init())

    def test_experimental_game_import_does_not_initialize_sdl(self):
        importlib.import_module("experiments.jojo_action_demo.main")
        self.assertFalse(pygame.get_init())

    def test_piano_import_does_not_create_tk_or_start_audio(self):
        importlib.import_module("ui.piano.main")
        self.assertIsNone(tk._default_root)
        self.assertIsNone(pygame.mixer.get_init())

    def test_desktop_import_does_not_create_a_root_or_start_audio(self):
        importlib.import_module("main_gui")
        self.assertIsNone(tk._default_root)
        self.assertIsNone(pygame.mixer.get_init())

    def test_antivirus_import_does_not_start_a_scan_or_create_a_window(self):
        importlib.import_module("core.antivirus")
        importlib.import_module("core.antivirus_window")
        self.assertIsNone(tk._default_root)
        self.assertFalse(pygame.get_init())

    def test_sprite_separator_import_does_not_open_a_window(self):
        importlib.import_module("games.separador_manual")
        self.assertIsNone(tk._default_root)

    def test_ikemen_tools_import_without_opening_a_window_or_audio(self):
        importlib.import_module("core.games.jojo_launcher")
        importlib.import_module("core.games.setup_ikemen_sbr")
        importlib.import_module("core.games.anime_character_import")
        importlib.import_module("core.games.hub_jogos")
        import main_gui

        self.assertTrue(callable(main_gui.JoJoOS.run_pygame))
        self.assertIsNone(tk._default_root)
        self.assertIsNone(pygame.mixer.get_init())


if __name__ == "__main__":
    unittest.main(verbosity=2)
