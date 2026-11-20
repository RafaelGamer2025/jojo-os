from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from core.games.android_data_package import (
    DATA_PACK_NAME,
    copy_android_character_data_pack,
    inspect_android_data_pack,
)


class AndroidDataPackageTests(unittest.TestCase):
    def _write_pack(self, path: Path, *, extra: dict[str, bytes] | None = None) -> str:
        manifest = {
            "engine_version": "v1.0.0",
            "character_count": 1,
            "series_counts": {"JoJo": 1},
            "characters": [
                {
                    "id": "test-jojo",
                    "display_name": "Teste",
                    "series": "JoJo",
                    "definition_path": "chars/Teste/Teste.def",
                    "sprite_files": ["chars/Teste/Teste.sff"],
                }
            ],
            "shared_dependencies": [],
        }
        members: dict[str, bytes] = {
            "MANIFEST.json": json.dumps(manifest).encode("utf-8"),
            "INSTALAR_NO_ANDROID.txt": b"Instrucoes de teste",
            "CREDITOS_E_ORIGEM.md": b"Creditos de teste",
            "data/select.def": (
                b"[Characters]\nTeste/Teste.def, stages/kfm.def\nrandomselect\n"
            ),
            "chars/Teste/Teste.def": b"[Info]\nname=Teste\n[Files]\nsprite=Teste.sff\n",
            "chars/Teste/Teste.sff": b"sprite test fixture, never executed",
        }
        if extra:
            members.update(extra)
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in members.items():
                archive.writestr(name, content)
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_validates_roster_paths_and_series_counts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            package = Path(temp_dir) / "valid.zip"
            self._write_pack(package)

            manifest = inspect_android_data_pack(
                package,
                expected_engine_version="v1.0.0",
                expected_character_count=1,
            )

            self.assertEqual(manifest["character_count"], 1)
            self.assertEqual(manifest["series_counts"], {"JoJo": 1})

    def test_rejects_incompatible_engine_version(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            package = Path(temp_dir) / "valid.zip"
            self._write_pack(package)

            with self.assertRaisesRegex(RuntimeError, "versão compatível"):
                inspect_android_data_pack(package, expected_engine_version="v2.0.0", expected_character_count=1)

    def test_rejects_wrong_character_count(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            package = Path(temp_dir) / "valid.zip"
            self._write_pack(package)

            with self.assertRaisesRegex(RuntimeError, "personagens"):
                inspect_android_data_pack(package, expected_character_count=44)

    def test_rejects_zip_slip_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            package = Path(temp_dir) / "unsafe.zip"
            self._write_pack(package, extra={"../escape.txt": b"no"})

            with self.assertRaisesRegex(RuntimeError, "caminho inseguro"):
                inspect_android_data_pack(package, expected_character_count=1)
            self.assertFalse((Path(temp_dir) / "escape.txt").exists())

    def test_rejects_unicode_control_character_in_member_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            package = Path(temp_dir) / "unsafe-control.zip"
            self._write_pack(package, extra={"chars/Teste/bad\x81.txt": b"metadata"})

            with self.assertRaisesRegex(RuntimeError, "caminho inseguro"):
                inspect_android_data_pack(package, expected_character_count=1)

    def test_rejects_executable_or_nested_archive(self) -> None:
        for member in ("chars/Teste/untrusted.exe", "chars/Teste/embedded.zip"):
            with self.subTest(member=member), tempfile.TemporaryDirectory() as temp_dir:
                package = Path(temp_dir) / "unsafe.zip"
                self._write_pack(package, extra={member: b"not executed"})

                with self.assertRaisesRegex(RuntimeError, "executável/arquivo aninhado"):
                    inspect_android_data_pack(package, expected_character_count=1)

    def test_rejects_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            package = Path(temp_dir) / "symlink.zip"
            self._write_pack(package)
            with zipfile.ZipFile(package, "a") as archive:
                info = zipfile.ZipInfo("chars/Teste/link")
                info.create_system = 3
                info.external_attr = (0o120777 << 16)
                archive.writestr(info, b"../../outside")

            with self.assertRaisesRegex(RuntimeError, "link simbólico"):
                inspect_android_data_pack(package, expected_character_count=1)

    def test_atomic_copy_verifies_hash_and_reuses_identical_package(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package = root / "source.zip"
            expected_hash = self._write_pack(package)
            destination = root / "Downloads"
            progress: list[tuple[str, int, int]] = []

            first = copy_android_character_data_pack(
                destination,
                lambda message, current, total: progress.append((message, current, total)),
                source_pack=package,
                expected_sha256=expected_hash,
                expected_engine_version="v1.0.0",
                expected_character_count=1,
            )
            second = copy_android_character_data_pack(
                destination,
                source_pack=package,
                expected_sha256=expected_hash,
                expected_engine_version="v1.0.0",
                expected_character_count=1,
            )

            self.assertEqual(first, destination / DATA_PACK_NAME)
            self.assertEqual(second, first)
            self.assertEqual(first.read_bytes(), package.read_bytes())
            self.assertTrue(progress)
            self.assertFalse(list(destination.glob("*.tmp")))

    def test_hash_failure_keeps_previous_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package = root / "source.zip"
            self._write_pack(package)
            destination = root / "Downloads"
            destination.mkdir()
            target = destination / DATA_PACK_NAME
            target.write_bytes(b"previous good copy")

            with self.assertRaisesRegex(RuntimeError, "SHA-256/tamanho"):
                copy_android_character_data_pack(
                    destination,
                    source_pack=package,
                    expected_sha256="1" * 64,
                    expected_engine_version="v1.0.0",
                    expected_character_count=1,
                )

            self.assertEqual(target.read_bytes(), b"previous good copy")
            self.assertFalse(list(destination.glob(".jojo-android-data-*.tmp")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
