from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from core.games import jojo_launcher
from core.games.setup_ikemen_sbr import (
    SBR_BUNDLED_FOLDER_MAP,
    SBR_CHARACTERS,
    setup_game,
)


class FakeResponse:
    def __init__(self, data: bytes, url: str):
        self._buffer = io.BytesIO(data)
        self._url = url
        self.headers = {"Content-Length": str(len(data))}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size: int = -1) -> bytes:
        return self._buffer.read(size)

    def geturl(self) -> str:
        return self._url


class IkemenSetupTests(unittest.TestCase):
    def test_setup_creates_layout_without_fake_characters(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "IKEMEN GO"
            result = setup_game(root)

            self.assertTrue((root / "chars").is_dir())
            self.assertTrue((root / "data" / "select.def").is_file())
            self.assertEqual(set(result.created_directories), set(SBR_CHARACTERS))
            self.assertEqual(result.registered, ())
            self.assertEqual(set(result.waiting_for_assets), set(SBR_CHARACTERS))
            self.assertTrue(result.select_def_changed)
            self.assertEqual(list((root / "chars").glob("*/*.def")), [])
            self.assertNotIn("Johnny_Joestar\n", (root / "data" / "select.def").read_text(encoding="utf-8"))

    def test_only_real_sbr_assets_are_registered_and_repeat_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            select_path = root / "data" / "select.def"
            select_path.parent.mkdir()
            select_path.write_text(
                "[ExtraStages]\n\nstage0 = stages/training.def\n\n[Characters]\nKFM, stages/kfm.def\n\n[Options]\n",
                encoding="utf-8",
            )
            johnny = root / "chars" / "Johnny_Joestar"
            johnny.mkdir(parents=True)
            (johnny / "Johnny.def").write_text("[Info]\nname = Johnny\n", encoding="utf-8")
            (johnny / "Johnny.sff").write_bytes(b"real-sprite-archive-placeholder-for-unit-test")
            # Gyro's .def without its sprite archive must not be registered.
            gyro = root / "chars" / "Gyro_Zeppeli"
            gyro.mkdir()
            (gyro / "Gyro.def").write_text("[Info]\nname = Gyro\n", encoding="utf-8")

            first = setup_game(root)
            text = select_path.read_text(encoding="utf-8")
            self.assertIn("Johnny_Joestar\n", text)
            self.assertIn("KFM, stages/kfm.def", text)
            self.assertIn("[Options]", text)
            self.assertNotIn("Gyro_Zeppeli\n", text)
            self.assertTrue(select_path.with_suffix(".def.bak").exists())
            self.assertEqual(first.registered, ("Johnny_Joestar",))
            self.assertTrue(first.select_def_changed)

            second = setup_game(root)
            self.assertFalse(second.select_def_changed)
            self.assertEqual(text.count("Johnny_Joestar\n"), 1)
            self.assertIn("Johnny.def", next(iter(johnny.glob("*.def"))).name)

    def test_release_asset_is_picked_from_official_stable_manifest(self) -> None:
        release = {
            "tag_name": "v1.0.0",
            "assets": [
                {"name": "Ikemen_GO-v1.0.0-linux.zip", "browser_download_url": "https://github.com/ikemen-engine/Ikemen-GO/releases/download/v1.0.0/Ikemen_GO-v1.0.0-linux.zip"},
                {"name": "Ikemen_GO-v1.0.0-windows.zip", "browser_download_url": "https://github.com/ikemen-engine/Ikemen-GO/releases/download/v1.0.0/Ikemen_GO-v1.0.0-windows.zip"},
            ],
        }
        asset = jojo_launcher.select_platform_asset(release, "windows")
        self.assertEqual(asset["name"], "Ikemen_GO-v1.0.0-windows.zip")
        with self.assertRaises(RuntimeError):
            jojo_launcher.select_platform_asset({"tag_name": "v1.0.0", "assets": []}, "windows")

    def test_android_release_selection_requires_exact_official_archive(self) -> None:
        release = {
            "tag_name": "v1.0.0",
            "assets": [
                {
                    "name": "Ikemen_GO-v1.0.0-android.zip",
                    "browser_download_url": (
                        "https://github.com/ikemen-engine/Ikemen-GO/releases/download/v1.0.0/"
                        "Ikemen_GO-v1.0.0-android.zip"
                    ),
                }
            ],
        }
        asset = jojo_launcher.select_android_asset(release)
        self.assertEqual(asset["name"], "Ikemen_GO-v1.0.0-android.zip")
        with self.assertRaisesRegex(RuntimeError, "não contém o pacote Android"):
            jojo_launcher.select_android_asset({"tag_name": "v1.0.0", "assets": []})

    def test_android_download_validates_apk_and_reuses_complete_copy(self) -> None:
        apk_buffer = io.BytesIO()
        with zipfile.ZipFile(apk_buffer, "w", compression=zipfile.ZIP_DEFLATED) as apk:
            apk.writestr("AndroidManifest.xml", b"manifest; test fixture")
            apk.writestr("lib/arm64-v8a/libmain.so", b"native Android library")
        archive_buffer = io.BytesIO()
        with zipfile.ZipFile(archive_buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("ikemen-go.apk", apk_buffer.getvalue())
            archive.writestr("README.md", "Official Android package instructions")
            archive.writestr("LICENSES.txt", "Official license notices")
            # These release-side build artifacts are not required for sideloading:
            # their runtime libraries are already inside the APK.
            archive.writestr("lib/libSDL2.so", b"release-side build output")
            archive.writestr("libmain.so", b"release-side build output")
        archive_bytes = archive_buffer.getvalue()
        digest = hashlib.sha256(archive_bytes).hexdigest()
        asset = {
            "name": "Ikemen_GO-v1.0.0-android.zip",
            "browser_download_url": (
                "https://github.com/ikemen-engine/Ikemen-GO/releases/download/v1.0.0/"
                "Ikemen_GO-v1.0.0-android.zip"
            ),
            "size": len(archive_bytes),
        }
        release = {"tag_name": "v1.0.0", "assets": [asset]}

        def fake_download(_asset, destination, expected_sha256, _progress=None):
            self.assertEqual(expected_sha256, digest)
            Path(destination).write_bytes(archive_bytes)

        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "android"
            with (
                patch.object(jojo_launcher, "get_latest_stable_release", return_value=release),
                patch.object(jojo_launcher, "select_android_asset", return_value=asset),
                patch.object(jojo_launcher, "_published_sha256", return_value=digest),
                patch.object(jojo_launcher, "_download_asset", side_effect=fake_download) as download,
            ):
                apk_path = jojo_launcher.download_android_ikemen(destination)
                self.assertTrue(jojo_launcher._is_valid_android_apk(apk_path))
                self.assertTrue((destination / "README.md").is_file())
                self.assertTrue((destination / "LICENSES.txt").is_file())
                self.assertFalse((destination / "lib").exists())
                self.assertFalse((destination / "libmain.so").exists())
                metadata = json.loads((destination / "download-info.json").read_text(encoding="utf-8"))
                self.assertEqual(metadata["version"], "v1.0.0")
                self.assertEqual(metadata["archive_sha256"], digest)
                self.assertEqual(metadata["apk_sha256"], jojo_launcher._sha256_file(apk_path))

                download.side_effect = AssertionError("A cópia Android íntegra deve ser reaproveitada")
                repeated = jojo_launcher.download_android_ikemen(destination)

            self.assertEqual(repeated, apk_path)
            download.assert_called_once()

    def test_bad_android_apk_preserves_previous_valid_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old_apk = io.BytesIO()
            with zipfile.ZipFile(old_apk, "w") as archive:
                archive.writestr("AndroidManifest.xml", b"previous valid fixture")
            apk_path = root / "ikemen-go.apk"
            apk_path.write_bytes(old_apk.getvalue())
            previous_bytes = apk_path.read_bytes()

            archive_path = root / "bad-android.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("ikemen-go.apk", b"not an APK")

            with self.assertRaisesRegex(RuntimeError, "não é um APK válido"):
                jojo_launcher._extract_android_apk(archive_path, root, "v1.0.1", "0" * 64)

            self.assertEqual(apk_path.read_bytes(), previous_bytes)
            self.assertEqual(list(root.glob(".ikemen-go-apk-*.tmp")), [])

    def test_installer_verifies_checksum_and_preserves_existing_select_def(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("Ikemen_GO.exe", b"fake exe bytes; never executed")
                archive.writestr("chars/kfm/kfm.def", "[Info]\nname = KFM\n")
                archive.writestr("data/select.def", "[Characters]\nKFM\n")
            zip_bytes = buffer.getvalue()
            digest = hashlib.sha256(zip_bytes).hexdigest()
            asset_name = "Ikemen_GO-v9.9.9-windows.zip"
            asset_url = jojo_launcher.OFFICIAL_RELEASE_PREFIX + "v9.9.9/" + asset_name
            release = {
                "tag_name": "v9.9.9",
                "draft": False,
                "prerelease": False,
                "assets": [
                    {
                        "name": asset_name,
                        "browser_download_url": asset_url,
                        "digest": "sha256:" + digest,
                        "size": len(zip_bytes),
                    }
                ],
            }
            manifest_bytes = json.dumps(release).encode("utf-8")
            responses = [
                FakeResponse(manifest_bytes, jojo_launcher.LATEST_RELEASE_API),
                FakeResponse(zip_bytes, asset_url),
            ]
            target = temp / "games" / "ikemen_go"
            target.mkdir(parents=True)
            (target / "data").mkdir()
            (target / "data" / "select.def").write_text("[Characters]\nMY_CUSTOM_CHAR\n", encoding="utf-8")
            (target / "chars").mkdir()
            (target / "chars" / "MY_CUSTOM_CHAR.txt").write_text("keep me", encoding="utf-8")

            with (
                patch("core.games.jojo_launcher.urllib.request.urlopen", side_effect=responses),
                patch("core.games.jojo_launcher.install_bundled_character_assets", return_value=()),
            ):
                result = jojo_launcher.install_latest_ikemen(target, platform_key="windows")

            self.assertEqual(result.version, "v9.9.9")
            self.assertTrue(result.downloaded)
            self.assertEqual(result.bundled_characters, ())
            self.assertTrue((target / "Ikemen_GO.exe").is_file())
            self.assertEqual((target / "data" / "select.def").read_text(encoding="utf-8"), "[Characters]\nMY_CUSTOM_CHAR\n")
            self.assertEqual((target / "chars" / "MY_CUSTOM_CHAR.txt").read_text(encoding="utf-8"), "keep me")
            self.assertIsNone(result.setup_result)
            self.assertFalse((target / "setup_ikemen_sbr.py").exists())
            self.assertFalse((target / "chars" / "Johnny_Joestar").exists())

    def test_prepare_installs_only_character_requested_by_download_button(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            game_dir = Path(temp_dir)
            with patch("core.games.jojo_launcher._platform_key", return_value="windows"):
                executable = game_dir / jojo_launcher.executable_name()
            executable.write_bytes(b"fake game executable; never executed")

            with (
                patch("core.games.jojo_launcher._platform_key", return_value="windows"),
                patch("core.games.jojo_launcher.find_installed_game_dir", return_value=game_dir),
                patch("core.games.jojo_launcher.install_bundled_character_assets", return_value=()) as install_chars,
            ):
                result = jojo_launcher.prepare_jojo_ikemen(character_series="jujutsu_kaisen")

            install_chars.assert_called_once_with(game_dir, series="jujutsu_kaisen")
            self.assertFalse(result.downloaded)
            self.assertEqual(result.bundled_characters, ())
            self.assertEqual(result.game_dir, game_dir)

    def test_prepare_without_character_series_does_not_install_anime(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            game_dir = Path(temp_dir)
            with patch("core.games.jojo_launcher._platform_key", return_value="windows"):
                executable = game_dir / jojo_launcher.executable_name()
            executable.write_bytes(b"fake game executable; never executed")

            with (
                patch("core.games.jojo_launcher._platform_key", return_value="windows"),
                patch("core.games.jojo_launcher.find_installed_game_dir", return_value=game_dir),
                patch("core.games.jojo_launcher.install_bundled_character_assets") as install_chars,
            ):
                result = jojo_launcher.prepare_jojo_ikemen()

            install_chars.assert_not_called()
            self.assertFalse(result.downloaded)
            self.assertEqual(result.bundled_characters, ())
            self.assertIsNone(result.setup_result)
            self.assertFalse((game_dir / "chars" / "Johnny_Joestar").exists())
            self.assertFalse((game_dir / "data" / "select.def").exists())

    def test_sbr_setup_is_created_only_when_explicitly_requested(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            game_dir = Path(temp_dir)
            with patch("core.games.jojo_launcher._platform_key", return_value="windows"):
                executable = game_dir / jojo_launcher.executable_name()
            executable.write_bytes(b"fake game executable; never executed")

            with (
                patch("core.games.jojo_launcher._platform_key", return_value="windows"),
                patch("core.games.jojo_launcher.find_installed_game_dir", return_value=game_dir),
                patch("core.games.jojo_launcher.install_bundled_character_assets", return_value=()) as install_chars,
            ):
                result = jojo_launcher.prepare_jojo_ikemen(setup_sbr=True)

            install_chars.assert_called_once_with(
                game_dir,
                series="jojo",
                folder_names=tuple(SBR_BUNDLED_FOLDER_MAP),
                destination_names=SBR_BUNDLED_FOLDER_MAP,
            )
            self.assertIsNotNone(result.setup_result)
            assert result.setup_result is not None
            self.assertEqual(len(result.setup_result.waiting_for_assets), 4)
            self.assertTrue((game_dir / "setup_ikemen_sbr.py").is_file())
            self.assertTrue((game_dir / "chars" / "Johnny_Joestar").is_dir())
            self.assertTrue((game_dir / "data" / "select.def").is_file())

    def test_sbr_setup_installs_included_diego_and_valentine_but_not_unverified_chars(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bundled = root / "bundled"
            for source_folder in SBR_BUNDLED_FOLDER_MAP:
                source = bundled / source_folder
                source.mkdir(parents=True)
                (source / f"{source_folder}.def").write_text(
                    f"[Info]\nname={source_folder}\n[Files]\nsprite={source_folder}.sff\n",
                    encoding="utf-8",
                )
                (source / f"{source_folder}.sff").write_bytes(b"fixture sprite archive")

            game_dir = root / "ikemen"
            game_dir.mkdir()
            (game_dir / "Ikemen_GO.exe").write_bytes(b"test fixture; never executed")
            with (
                patch("core.games.anime_character_import.BUNDLED_ASSETS_DIR", bundled),
                patch("core.games.jojo_launcher._platform_key", return_value="windows"),
                patch("core.games.jojo_launcher.find_installed_game_dir", return_value=game_dir),
            ):
                result = jojo_launcher.prepare_jojo_ikemen(setup_sbr=True)

            assert result.setup_result is not None
            self.assertEqual(result.bundled_characters, (
                "Diego_Brando/JoJo_Diego_Brando.def",
                "Funny_Valentine/JoJo_Funny_Valentine.def",
            ))
            self.assertEqual(result.setup_result.registered, ("Diego_Brando", "Funny_Valentine"))
            self.assertEqual(result.setup_result.waiting_for_assets, ("Johnny_Joestar", "Gyro_Zeppeli"))
            select_text = (game_dir / "data" / "select.def").read_text(encoding="utf-8")
            self.assertIn("Diego_Brando/JoJo_Diego_Brando.def\n", select_text)
            self.assertIn("Funny_Valentine/JoJo_Funny_Valentine.def\n", select_text)
            self.assertNotIn("Johnny_Joestar\n", select_text)
            self.assertNotIn("Gyro_Zeppeli\n", select_text)

    def test_fullscreen_config_preserves_settings_and_backups_before_change(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = root / "save" / "config.ini"
            config.parent.mkdir()
            original = "[Video]\nFullscreen = 0 ; keep comment\nWindowWidth = 1280\n[Sound]\nMasterVolume = 70\n"
            config.write_text(original, encoding="utf-8")

            result = jojo_launcher.configurar_tela_cheia(root)
            updated = config.read_text(encoding="utf-8")

            self.assertEqual(result, config)
            self.assertIn("Fullscreen = 1", updated)
            self.assertIn("WindowWidth = 1280", updated)
            self.assertIn("[Sound]\nMasterVolume = 70", updated)
            self.assertEqual(config.with_suffix(".ini.bak").read_text(encoding="utf-8"), original)

            jojo_launcher.configurar_tela_cheia(root)
            self.assertEqual(config.with_suffix(".ini.bak").read_text(encoding="utf-8"), original)

    def test_fullscreen_config_creates_minimal_user_config_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = jojo_launcher.configurar_tela_cheia(root)
            self.assertTrue(config.is_file())
            self.assertIn("[Video]", config.read_text(encoding="utf-8"))
            self.assertIn("Fullscreen = 1", config.read_text(encoding="utf-8"))
            self.assertFalse(config.with_suffix(".ini.bak").exists())

    def test_fullscreen_launcher_configures_before_starting_without_shell(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            executable = root / "Ikemen_GO.exe"
            executable.write_bytes(b"test fixture; never executed")
            (root / "chars").mkdir()
            (root / "data").mkdir()
            (root / "data" / "select.def").write_text("[Characters]\n", encoding="utf-8")
            with (
                patch("core.games.jojo_launcher._platform_key", return_value="windows"),
                patch("core.games.jojo_launcher.subprocess.Popen") as popen,
            ):
                success, message = jojo_launcher.lancar_jojo_ikemen(root)

            self.assertTrue(success, message)
            self.assertIn("iniciado", message)
            config = (root / "save" / "config.ini").read_text(encoding="utf-8")
            self.assertIn("Fullscreen = 1", config)
            popen.assert_called_once()
            self.assertFalse(popen.call_args.kwargs["shell"])

    def test_fullscreen_config_refuses_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            save = root / "save"
            save.mkdir()
            outside = root / "outside.ini"
            outside.write_text("[Video]\nFullscreen = 0\n", encoding="utf-8")
            config = save / "config.ini"
            try:
                config.symlink_to(outside)
            except (OSError, NotImplementedError):
                self.skipTest("O sistema não permite criar symlinks neste ambiente")
            with self.assertRaisesRegex(RuntimeError, "link simbólico"):
                jojo_launcher.configurar_tela_cheia(root)
            self.assertIn("Fullscreen = 0", outside.read_text(encoding="utf-8"))

    def test_zip_slip_archive_is_rejected_without_writing_outside(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive_path = root / "bad.zip"
            extract_dir = root / "unpacked"
            outside = root / "escape.txt"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("../escape.txt", "bad")
            with self.assertRaises(RuntimeError):
                jojo_launcher._safe_extract(archive_path, extract_dir)
            self.assertFalse(outside.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
