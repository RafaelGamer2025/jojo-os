from __future__ import annotations

import io
import json
import tempfile
import unittest
import urllib.error
import zipfile
from pathlib import Path
from unittest.mock import patch

from core.games import character_downloader as downloader


class FakeResponse:
    def __init__(self, data: bytes, url: str, headers: dict[str, str] | None = None):
        self._buffer = io.BytesIO(data)
        self._url = url
        self.headers = headers or {"Content-Length": str(len(data))}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size: int = -1) -> bytes:
        return self._buffer.read(size)

    def geturl(self) -> str:
        return self._url


class FakeOpener:
    def __init__(self, responses: list[FakeResponse | BaseException]):
        self.responses = responses
        self.requests = []

    def open(self, request, timeout: int = 60) -> FakeResponse:
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("Unexpected HTTP request")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return buffer.getvalue()


class CharacterDownloaderTests(unittest.TestCase):
    def test_bundled_catalog_installs_only_selected_character_and_reuses_it(self) -> None:
        cases = (
            ("jojo_diego", "JoJo_Diego_Brando", "Diego_Brando", "jojo"),
            ("jojo_funny_valentine", "JoJo_Funny_Valentine", "Funny_Valentine", "jojo"),
            ("jojo_jotaro_m_ism", "JoJo_Jotaro_M_Ism", "JoJo_Jotaro_M_Ism", "jojo"),
            ("jojo_wonder_of_u", "JoJo_Wonder_Of_You", "JoJo_Wonder_Of_You", "jojo"),
            ("one_piece_zoro", "OnePiece_Roronoa_Zoro", "OnePiece_Roronoa_Zoro", "one_piece"),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bundled = root / "assets"
            for _character_id, source_folder, _target_folder, series in cases:
                source_dir = bundled / source_folder
                source_dir.mkdir(parents=True)
                (source_dir / f"{source_folder}.def").write_text(
                    f"[Info]\nname={source_folder}\n[Files]\nsprite={source_folder}.sff\n",
                    encoding="utf-8",
                )
                (source_dir / f"{source_folder}.sff").write_bytes(b"bundled-sprite-fixture")
                (source_dir / "JOJO_OS_ORIGEM.txt").write_text(f"series={series}", encoding="utf-8")

            with patch("core.games.anime_character_import.BUNDLED_ASSETS_DIR", bundled):
                for character_id, source_folder, target_folder, _series in cases:
                    with self.subTest(character_id=character_id):
                        game_dir = root / "games" / character_id
                        first = downloader.install_selected_character(game_dir, character_id)
                        second = downloader.install_selected_character(game_dir, character_id)

                        self.assertEqual(first.folder_name, target_folder)
                        self.assertTrue((first.character_dir / f"{source_folder}.sff").is_file())
                        self.assertFalse(second.select_def_changed)
                        installed_dirs = [path.name for path in (game_dir / "chars").iterdir() if path.is_dir()]
                        self.assertEqual(installed_dirs, [target_folder])
                        select_text = (game_dir / "data" / "select.def").read_text(encoding="utf-8")
                        self.assertEqual(select_text.count(first.character_entry), 1)

    def test_github_character_files_are_hash_checked_and_installed(self) -> None:
        definition = b"[Info]\nname = Jonathan\n[Files]\nsprite = jonathan_asb.sff\n"
        sprites = b"small test SFF; never executed"
        raw_base = "https://raw.githubusercontent.com/amarimono-mugen/products/"
        raw_def = raw_base + downloader.GITHUB_COMMIT + "/jonathan_asb/jonathan_asb.def"
        raw_sff = raw_base + downloader.GITHUB_COMMIT + "/jonathan_asb/jonathan_asb.sff"
        payload = {
            "truncated": False,
            "tree": [
                {
                    "path": "jonathan_asb/jonathan_asb.def",
                    "type": "blob",
                    "mode": "100644",
                    "size": len(definition),
                    "sha": downloader._git_blob_sha(definition),
                },
                {
                    "path": "jonathan_asb/jonathan_asb.sff",
                    "type": "blob",
                    "mode": "100644",
                    "size": len(sprites),
                    "sha": downloader._git_blob_sha(sprites),
                },
            ],
        }
        tree_bytes = json.dumps(payload).encode("utf-8")

        with tempfile.TemporaryDirectory() as temp_dir:
            game_dir = Path(temp_dir) / "game"

            def fake_urlopen(request, timeout: int = 60) -> FakeResponse:
                url = request.full_url
                if url == downloader.GITHUB_TREE_URL:
                    return FakeResponse(tree_bytes, url)
                if url == raw_def:
                    return FakeResponse(definition, url)
                if url == raw_sff:
                    return FakeResponse(sprites, url)
                raise AssertionError(f"Unexpected URL: {url}")

            with patch("core.games.character_downloader.urllib.request.urlopen", side_effect=fake_urlopen):
                result = downloader.install_selected_character(game_dir, "jojo_jonathan")

            self.assertEqual(result.series, "JoJo")
            self.assertEqual(result.character_entry, "JoJo_jonathan_asb/jonathan_asb.def")
            self.assertTrue((result.character_dir / "jonathan_asb.sff").is_file())
            self.assertTrue((result.character_dir / "JOJO_OS_ORIGEM.txt").is_file())
            select_text = (game_dir / "data" / "select.def").read_text(encoding="utf-8")
            self.assertEqual(select_text.count(result.character_entry), 1)

            with patch(
                "core.games.character_downloader.urllib.request.urlopen",
                side_effect=AssertionError("A repetição não deve consultar a rede"),
            ):
                repeated = downloader.install_selected_character(game_dir, "jojo_jonathan")
            self.assertFalse(repeated.select_def_changed)
            self.assertEqual(repeated.character_dir, result.character_dir)
            select_text = (game_dir / "data" / "select.def").read_text(encoding="utf-8")
            self.assertEqual(select_text.count(result.character_entry), 1)

    def test_itch_flow_uses_free_button_and_extracts_only_goku(self) -> None:
        source = downloader._CHARACTER_SOURCES["dragonball_goku"]
        host = f"{source.itch_user}.itch.io"
        base = f"https://{host}/{source.itch_slug}"
        download_page_url = f"{base}/download/free-token"
        direct_url = "https://download.itch.zone/12345/goku.zip"
        archive_bytes = _zip_bytes(
            {
                "Goku Pack/chars/Goku/Goku.def": b"[Info]\nname = Goku\n[Files]\nsprite = Goku.sff\n",
                "Goku Pack/chars/Goku/Goku.sff": b"goku sprites; never executed",
                "Goku Pack/stages/KameHouse.def": b"stage; not extracted",
                "Goku Pack/Ikemen_GO.exe": b"exe; not extracted or executed",
            }
        )
        purchase_html = (
            '<input type="hidden" name="csrf_token" value="csrf-purchase">'
            "<button>No thanks, just take me to the downloads</button>"
            f"{source.itch_filename}"
        ).encode()
        download_html = (
            '<input type="hidden" name="csrf_token" value="csrf-download">'
            f'<button class="button download_btn" data-upload_id="123">{source.itch_filename}</button>'
        ).encode()
        fake_opener = FakeOpener(
            [
                FakeResponse(purchase_html, f"https://{host}/{source.itch_slug}/purchase"),
                FakeResponse(json.dumps({"url": download_page_url}).encode(), f"https://{host}/download_url"),
                FakeResponse(download_html, download_page_url),
                FakeResponse(json.dumps({"url": direct_url}).encode(), f"https://{host}/{source.itch_slug}/file/123"),
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir)
            with (
                patch("core.games.character_downloader.urllib.request.build_opener", return_value=fake_opener),
                patch(
                    "core.games.character_downloader.urllib.request.urlopen",
                    return_value=FakeResponse(
                        archive_bytes,
                        direct_url,
                        {"Content-Length": str(len(archive_bytes))},
                    ),
                ),
            ):
                archive = downloader._download_itch_archive(source, destination)
                character_dir = downloader._extract_archive_character(archive, source, destination)

            self.assertEqual(character_dir.name, "Goku")
            self.assertTrue((character_dir / "Goku.def").is_file())
            self.assertTrue((character_dir / "Goku.sff").is_file())
            self.assertTrue((character_dir / "JOJO_OS_ORIGEM.txt").is_file())
            self.assertFalse(any(character_dir.rglob("*.exe")))
            requested_urls = [request.full_url for request in fake_opener.requests]
            self.assertIn(f"{base}/download_url", requested_urls)
            self.assertIn(f"https://{host}/{source.itch_slug}/file/123?source=game_download", requested_urls)
            self.assertFalse(any("checkout" in url.casefold() for url in requested_urls))

    def test_itch_429_stops_without_scraping_or_fallback(self) -> None:
        source = downloader._CHARACTER_SOURCES["dragonball_goku"]
        base = f"https://{source.itch_user}.itch.io/{source.itch_slug}"
        error = urllib.error.HTTPError(base + "/purchase", 429, "Too Many Requests", {}, io.BytesIO())
        fake_opener = FakeOpener([error])
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch("core.games.character_downloader.urllib.request.build_opener", return_value=fake_opener),
            self.assertRaisesRegex(RuntimeError, "limitou temporariamente"),
        ):
            downloader._download_itch_archive(source, Path(temp_dir))
        self.assertEqual(len(fake_opener.requests), 1)
        self.assertEqual(fake_opener.requests[0].full_url, base + "/purchase")

    def test_free_one_piece_download_page_without_purchase_route_extracts_only_luffy(self) -> None:
        source = downloader._CHARACTER_SOURCES["one_piece_luffy"]
        host = f"{source.itch_user}.itch.io"
        base = f"https://{host}/{source.itch_slug}"
        download_page_url = base + "/download"
        direct_url = "https://download.itch.zone/54321/one-piece.zip"
        archive_bytes = _zip_bytes(
            {
                "One Piece/chars/Luffy/Luffy.def": b"[Info]\nname=Luffy\n[Files]\nsprite=Luffy.sff\n",
                "One Piece/chars/Luffy/Luffy.sff": b"luffy sprites; never executed",
                "One Piece/chars/Zoro/Zoro.def": b"other character; not extracted",
                "One Piece/Ikemen_GO.exe": b"not extracted or executed",
            }
        )
        direct_page = (
            '<input type="hidden" name="csrf_token" value="csrf-one-piece">'
            f'<button class="button download_btn" data-upload_id="456">{source.itch_filename}</button>'
        ).encode()
        fake_opener = FakeOpener(
            [
                downloader._ItchHTTPError(404, "free product has no purchase route"),
                FakeResponse(direct_page, download_page_url),
                FakeResponse(
                    json.dumps({"url": direct_url}).encode(),
                    f"https://{host}/{source.itch_slug}/file/456",
                ),
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir)
            with (
                patch("core.games.character_downloader.urllib.request.build_opener", return_value=fake_opener),
                patch(
                    "core.games.character_downloader.urllib.request.urlopen",
                    return_value=FakeResponse(archive_bytes, direct_url),
                ),
            ):
                archive = downloader._download_itch_archive(source, destination)
                character_dir = downloader._extract_archive_character(archive, source, destination)

            self.assertEqual(character_dir.name, "Luffy")
            self.assertTrue((character_dir / "Luffy.def").is_file())
            self.assertTrue((character_dir / "Luffy.sff").is_file())
            self.assertFalse(any(character_dir.rglob("*.exe")))
            requested_urls = [request.full_url for request in fake_opener.requests]
            self.assertEqual(requested_urls[0], base + "/purchase")
            self.assertEqual(requested_urls[1], download_page_url)
            self.assertIn(f"https://{host}/{source.itch_slug}/file/456?source=game_download", requested_urls)

            game_dir = destination / "game"

            def save_one_piece_archive(_source, temp_path, progress=None):
                archive_path = Path(temp_path) / "one-piece-source.zip"
                archive_path.write_bytes(archive_bytes)
                return archive_path

            with patch.object(downloader, "_download_itch_archive", side_effect=save_one_piece_archive):
                installed = downloader.install_selected_character(game_dir, "one_piece_luffy")
            self.assertEqual(installed.character_entry, "OnePiece_Luffy/Luffy.def")
            self.assertEqual(
                (game_dir / "data" / "select.def").read_text(encoding="utf-8").count(installed.character_entry),
                1,
            )
            with patch.object(
                downloader,
                "_download_itch_archive",
                side_effect=AssertionError("Luffy instalado não deve ser baixado novamente"),
            ):
                repeated = downloader.install_selected_character(game_dir, "one_piece_luffy")
            self.assertFalse(repeated.select_def_changed)

    def test_archive_extractor_rejects_zip_slip_before_writing(self) -> None:
        source = downloader._CHARACTER_SOURCES["one_piece_luffy"]
        bad_archive = _zip_bytes(
            {
                "Game/chars/Luffy/Luffy.def": b"[Info]\nname=Luffy\n[Files]\nsprite=Luffy.sff\n",
                "Game/chars/Luffy/Luffy.sff": b"sprites",
                "Game/chars/Luffy/../../escape.txt": b"outside",
            }
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive_path = root / "bad.zip"
            archive_path.write_bytes(bad_archive)
            with self.assertRaisesRegex(RuntimeError, "caminho inseguro"):
                downloader._extract_archive_character(archive_path, source, root)
            self.assertFalse((root / "escape.txt").exists())

    def test_batch_continues_after_source_failure_and_reuses_github_tree(self) -> None:
        sources = (
            downloader.CharacterSource("local", "Pacote local", "jojo", "bundled"),
            downloader.CharacterSource(
                "github_bad", "Fonte GitHub", "jojo", "github",
                github_folder="fighter", github_definition="fighter.def",
            ),
            downloader.CharacterSource("itch_ok", "Fonte itch", "one_piece", "itch"),
        )
        tree_payload = {"truncated": False, "tree": []}
        calls: list[tuple[str, dict | None]] = []
        progress_updates: list[tuple[str, int, int]] = []

        def fake_install(_root, character_id, progress=None, *, _github_tree_payload=None):
            calls.append((character_id, _github_tree_payload))
            if character_id == "github_bad":
                raise RuntimeError("fonte temporariamente indisponível")

        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch.object(downloader, "character_catalog", return_value=sources),
            patch.object(downloader, "_register_existing_download", return_value=None),
            patch.object(downloader, "_read_github_json", return_value=tree_payload) as read_tree,
            patch.object(downloader, "install_selected_character", side_effect=fake_install),
        ):
            result = downloader.install_all_characters(
                Path(temp_dir), progress=lambda message, current, total: progress_updates.append(
                    (message, current, total)
                )
            )

        self.assertEqual(result.total, 3)
        self.assertEqual(result.completed, ("local", "itch_ok"))
        self.assertEqual([failure.character_id for failure in result.failures], ["github_bad"])
        self.assertIn("temporariamente indisponível", result.failures[0].error)
        self.assertEqual([character_id for character_id, _payload in calls], ["local", "github_bad", "itch_ok"])
        self.assertIsNone(calls[0][1])
        self.assertEqual(calls[1][1], tree_payload)
        self.assertIsNone(calls[2][1])
        read_tree.assert_called_once_with(downloader.GITHUB_TREE_URL)
        self.assertEqual(progress_updates[-1][1:], (3000, 3000))


if __name__ == "__main__":
    unittest.main(verbosity=2)
