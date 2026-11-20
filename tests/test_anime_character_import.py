from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.games.anime_character_import import (
    import_character_folder,
    install_bundled_character_assets,
)


class AnimeCharacterImportTests(unittest.TestCase):
    def _make_character(self, root: Path, name: str = "Gojo") -> Path:
        character = root / name
        character.mkdir(parents=True)
        (character / f"{name}.def").write_text(
            f"[Info]\nname = {name}\n[Files]\nsprite = {name}.sff\n",
            encoding="utf-8",
        )
        (character / f"{name}.sff").write_bytes(b"sprite-archive-placeholder-for-unit-test")
        (character / "README.txt").write_text("Author credits remain with the package.", encoding="utf-8")
        return character

    def test_import_copies_local_character_and_registers_explicit_def_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            game_dir = root / "game"
            (game_dir / "data").mkdir(parents=True)
            select_path = game_dir / "data" / "select.def"
            original_select = "[Characters]\nkfm\n\n[Options]\narcade.maxmatches = 6,1\n"
            select_path.write_text(original_select, encoding="utf-8")
            source = self._make_character(root / "downloads")

            result = import_character_folder(
                game_dir,
                "jujutsu_kaisen",
                source,
                permission_confirmed=True,
            )

            self.assertEqual(result.series, "Jujutsu Kaisen")
            self.assertEqual(result.folder_name, "JujutsuKaisen_Gojo")
            self.assertEqual(result.character_entry, "JujutsuKaisen_Gojo/Gojo.def")
            self.assertTrue((result.character_dir / "Gojo.sff").is_file())
            self.assertTrue((result.character_dir / "README.txt").is_file())
            self.assertTrue(result.select_def_changed)
            updated = select_path.read_text(encoding="utf-8")
            self.assertIn("JujutsuKaisen_Gojo/Gojo.def", updated)
            self.assertLess(updated.index("JujutsuKaisen_Gojo/Gojo.def"), updated.index("[Options]"))
            self.assertEqual(select_path.with_suffix(".def.bak").read_text(encoding="utf-8"), original_select)

    def test_naruto_import_uses_safe_folder_prefix_and_keeps_existing_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            game_dir = root / "game"
            (game_dir / "data").mkdir(parents=True)
            select_path = game_dir / "data" / "select.def"
            select_path.write_text("[Characters]\nkfm\n[ExtraStages]\nstages/training.def\n", encoding="utf-8")
            source = self._make_character(root / "download" / "Naruto Uzumaki", "Naruto Uzumaki")

            result = import_character_folder(game_dir, "naruto", source, permission_confirmed=True)

            self.assertEqual(result.folder_name, "Naruto_Naruto_Uzumaki")
            content = select_path.read_text(encoding="utf-8")
            self.assertIn("kfm\n", content)
            self.assertIn("Naruto_Naruto_Uzumaki/Naruto Uzumaki.def", content)
            self.assertIn("[ExtraStages]", content)

    def test_jojo_dragon_ball_and_one_piece_use_distinct_safe_prefixes(self) -> None:
        cases = (
            ("jojo", "JoJo", "JoJo_TestChar"),
            ("dragon_ball", "Dragon Ball Z", "DragonBallZ_TestChar"),
            ("one_piece", "One Piece", "OnePiece_TestChar"),
        )
        for series, expected_label, expected_folder in cases:
            with self.subTest(series=series), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                source = self._make_character(root / "downloads", "TestChar")
                result = import_character_folder(
                    root / "game",
                    series,
                    source,
                    permission_confirmed=True,
                )

                self.assertEqual(result.series, expected_label)
                self.assertEqual(result.folder_name, expected_folder)
                self.assertEqual(result.character_entry, f"{expected_folder}/TestChar.def")
                select_text = (root / "game" / "data" / "select.def").read_text(encoding="utf-8")
                self.assertEqual(select_text.count(result.character_entry), 1)

    def test_permission_acknowledgement_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = self._make_character(root / "downloads")
            with self.assertRaises(PermissionError):
                import_character_folder(root / "game", "naruto", source)

    def test_incomplete_character_is_rejected_before_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            game_dir = root / "game"
            source = root / "downloads" / "Incomplete"
            source.mkdir(parents=True)
            (source / "Incomplete.def").write_text("[Info]\nname=Incomplete\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, r"\.sff"):
                import_character_folder(game_dir, "naruto", source, permission_confirmed=True)
            self.assertFalse((game_dir / "chars").exists())

    def test_existing_destination_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            game_dir = root / "game"
            first_source = self._make_character(root / "one")
            second_source = self._make_character(root / "two")

            first = import_character_folder(game_dir, "naruto", first_source, permission_confirmed=True)
            marker = first.character_dir / "keep.txt"
            marker.write_text("keep", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                import_character_folder(game_dir, "naruto", second_source, permission_confirmed=True)
            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")

    def test_unknown_series_and_ambiguous_definitions_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = self._make_character(root / "downloads")
            with self.assertRaisesRegex(ValueError, "Série não reconhecida"):
                import_character_folder(root / "game", "bleach", source, permission_confirmed=True)

            (source / "Gojo_Alt.def").write_text("[Info]\nname=Gojo Alt\n", encoding="utf-8")
            (source / "Gojo.def").rename(source / "Gojo_Main.def")
            with self.assertRaisesRegex(ValueError, r"vários arquivos \.def"):
                import_character_folder(root / "game", "jujutsu_kaisen", source, permission_confirmed=True)

    def test_bundled_characters_are_copied_registered_once_and_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bundled = root / "assets"
            self._make_character(bundled, "Naruto_Naruto_Uzumaki")
            self._make_character(bundled, "JujutsuKaisen_Yuji_Itadori")
            game_dir = root / "game"
            (game_dir / "data").mkdir(parents=True)
            select_path = game_dir / "data" / "select.def"
            select_path.write_text("[Characters]\nkfm\n\n[Options]\n", encoding="utf-8")

            with patch("core.games.anime_character_import.BUNDLED_ASSETS_DIR", bundled):
                first = install_bundled_character_assets(game_dir)
                self.assertEqual({item.series for item in first}, {"Naruto", "Jujutsu Kaisen"})
                self.assertEqual(len(first), 2)
                for result in first:
                    self.assertTrue((result.character_dir / f"{result.folder_name}.def").is_file())
                    self.assertTrue((result.character_dir / f"{result.folder_name}.sff").is_file())
                    (result.character_dir / "preserve.txt").write_text("keep", encoding="utf-8")

                second = install_bundled_character_assets(game_dir)

            self.assertEqual(len(second), 2)
            self.assertFalse(any(result.select_def_changed for result in second))
            content = select_path.read_text(encoding="utf-8")
            for result in second:
                self.assertEqual(content.count(result.character_entry), 1)
                self.assertEqual((result.character_dir / "preserve.txt").read_text(encoding="utf-8"), "keep")

    def test_bundled_character_button_installs_only_requested_series(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bundled = root / "assets"
            self._make_character(bundled, "Naruto_Naruto_Uzumaki")
            self._make_character(bundled, "JujutsuKaisen_Yuji_Itadori")
            game_dir = root / "game"

            with patch("core.games.anime_character_import.BUNDLED_ASSETS_DIR", bundled):
                result = install_bundled_character_assets(game_dir, series="jujutsu_kaisen")

            self.assertEqual(len(result), 1)
            self.assertEqual(result[0].series, "Jujutsu Kaisen")
            self.assertTrue((game_dir / "chars" / "JujutsuKaisen_Yuji_Itadori" / "JujutsuKaisen_Yuji_Itadori.sff").is_file())
            self.assertFalse((game_dir / "chars" / "Naruto_Naruto_Uzumaki").exists())
            select_text = (game_dir / "data" / "select.def").read_text(encoding="utf-8")
            self.assertEqual(select_text.count(result[0].character_entry), 1)

            with self.assertRaisesRegex(ValueError, "Série não reconhecida"):
                install_bundled_character_assets(game_dir, series="bleach")

    def test_bundled_folder_filter_uses_canonical_sbr_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bundled = root / "assets"
            self._make_character(bundled, "JoJo_Diego_Brando")
            self._make_character(bundled, "JoJo_Funny_Valentine")
            game_dir = root / "game"
            folder_map = {"JoJo_Diego_Brando": "Diego_Brando"}

            with patch("core.games.anime_character_import.BUNDLED_ASSETS_DIR", bundled):
                first = install_bundled_character_assets(
                    game_dir,
                    series="jojo",
                    folder_names=("JoJo_Diego_Brando",),
                    destination_names=folder_map,
                )
                second = install_bundled_character_assets(
                    game_dir,
                    series="jojo",
                    folder_names=("JoJo_Diego_Brando",),
                    destination_names=folder_map,
                )

            self.assertEqual(len(first), 1)
            self.assertEqual(first[0].folder_name, "Diego_Brando")
            self.assertEqual(first[0].character_entry, "Diego_Brando/JoJo_Diego_Brando.def")
            self.assertTrue((game_dir / "chars" / "Diego_Brando" / "JoJo_Diego_Brando.sff").is_file())
            self.assertFalse((game_dir / "chars" / "JoJo_Funny_Valentine").exists())
            self.assertFalse(second[0].select_def_changed)
            select_text = (game_dir / "data" / "select.def").read_text(encoding="utf-8")
            self.assertEqual(select_text.count(first[0].character_entry), 1)

    def test_symbolic_links_are_rejected_when_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = self._make_character(root / "downloads")
            outside = root / "outside.txt"
            outside.write_text("outside", encoding="utf-8")
            try:
                (source / "outside-link.txt").symlink_to(outside)
            except (OSError, NotImplementedError):
                self.skipTest("O sistema não permite criar symlinks neste ambiente")

            with self.assertRaisesRegex(ValueError, "link simbólico"):
                import_character_folder(root / "game", "naruto", source, permission_confirmed=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
