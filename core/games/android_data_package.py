"""Validação e cópia do pacote de personagens para a release Android oficial.

O APK oficial permanece intacto. Este arquivo de dados é copiado ao lado dele e
mesclado manualmente na pasta escolhida dentro do app Android.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
import unicodedata
import zipfile
from collections import Counter
from collections.abc import Callable
from pathlib import Path, PurePosixPath, PureWindowsPath

DATA_PACK_NAME = "JoJo_OS_Android_DataPack.zip"
DATA_PACK_ENGINE_VERSION = "v1.0.0"
DATA_PACK_CHARACTER_COUNT = 44
DATA_PACK_SHA256 = "2e422b8fbcb4c535e031302d8843141052b8c72538365b278d9c727cb190ff48"
MAX_DATA_PACK_BYTES = 2 * 1024 * 1024 * 1024
MAX_DATA_PACK_ENTRIES = 50_000
CHUNK_SIZE = 256 * 1024
BLOCKED_SUFFIXES = {
    ".apk", ".exe", ".dll", ".so", ".dylib", ".bat", ".sh", ".py", ".ps1", ".com",
    ".zip", ".rar", ".7z",
}
ProgressCallback = Callable[[str, int, int], None]


def bundled_android_data_pack() -> Path:
    """Return the private data archive shipped next to this module."""
    return Path(__file__).with_name(DATA_PACK_NAME)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_member_name(name: str) -> PurePosixPath:
    normalized = name.replace("\\", "/")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(normalized)
    if (
        not posix.parts
        or posix.is_absolute()
        or windows.is_absolute()
        or windows.drive
        or any(part in {"", ".", ".."} for part in posix.parts)
        or any(any(unicodedata.category(char) == "Cc" for char in part) for part in posix.parts)
    ):
        raise RuntimeError(f"O pacote Android contém caminho inseguro: {name!r}.")
    return posix


def _characters_section_entries(text: str) -> set[str]:
    entries: set[str] = set()
    active = False
    for line in text.splitlines():
        value = line.strip()
        if value.startswith("[") and value.endswith("]"):
            active = value.casefold() == "[characters]"
            continue
        if not active:
            continue
        entry = value.split(";", 1)[0].split(",", 1)[0].strip().replace("\\", "/")
        if entry and entry.casefold() != "randomselect":
            entries.add(entry.casefold())
    return entries


def inspect_android_data_pack(
    pack_path: str | Path,
    *,
    expected_engine_version: str | None = DATA_PACK_ENGINE_VERSION,
    expected_character_count: int | None = DATA_PACK_CHARACTER_COUNT,
) -> dict:
    """Check archive structure, roster references and safe paths without extracting it."""
    source = Path(pack_path).expanduser()
    if source.is_symlink() or not source.is_file():
        raise RuntimeError("O pacote de dados Android não existe ou não é um arquivo normal.")
    if source.stat().st_size <= 0 or source.stat().st_size > MAX_DATA_PACK_BYTES:
        raise RuntimeError("O tamanho do pacote de dados Android é inválido ou excede 2 GiB.")
    try:
        archive = zipfile.ZipFile(source)
    except (OSError, zipfile.BadZipFile) as exc:
        raise RuntimeError("O pacote de dados Android não é um ZIP válido.") from exc

    with archive:
        infos = archive.infolist()
        if not infos or len(infos) > MAX_DATA_PACK_ENTRIES:
            raise RuntimeError("O pacote Android está vazio ou contém arquivos demais.")
        if sum(info.file_size for info in infos) > MAX_DATA_PACK_BYTES:
            raise RuntimeError("O conteúdo do pacote Android excede 2 GiB descompactado.")

        exact_names: set[str] = set()
        folded_names: set[str] = set()
        allowed_root_files = {
            "MANIFEST.json",
            "INSTALAR_NO_ANDROID.txt",
            "CREDITOS_E_ORIGEM.md",
        }
        allowed_data_files = {"data/select.def", "data/common1.cns"}
        for info in infos:
            member = _validate_member_name(info.filename)
            name = member.as_posix()
            if name in exact_names or name.casefold() in folded_names:
                raise RuntimeError(f"O pacote Android contém um caminho duplicado: {name!r}.")
            exact_names.add(name)
            folded_names.add(name.casefold())

            mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(mode):
                raise RuntimeError(f"O pacote Android contém link simbólico: {name!r}.")
            if info.is_dir():
                if member.parts[0].casefold() not in {"chars", "data"}:
                    raise RuntimeError(f"O pacote Android contém pasta fora do escopo: {name!r}.")
                continue
            if member.parts[0] == "chars":
                if len(member.parts) < 3:
                    raise RuntimeError(f"Caminho de personagem incompleto: {name!r}.")
                if member.suffix.casefold() in BLOCKED_SUFFIXES:
                    raise RuntimeError(f"O pacote de personagens contém executável/arquivo aninhado: {name!r}.")
            elif name in allowed_data_files or (len(member.parts) == 1 and name in allowed_root_files):
                pass
            else:
                raise RuntimeError(f"Arquivo fora do escopo permitido no pacote Android: {name!r}.")

        required = {
            "MANIFEST.json",
            "INSTALAR_NO_ANDROID.txt",
            "CREDITOS_E_ORIGEM.md",
            "data/select.def",
        }
        missing = required - exact_names
        if missing:
            raise RuntimeError("O pacote Android não contém: " + ", ".join(sorted(missing)))

        try:
            manifest = json.loads(archive.read("MANIFEST.json").decode("utf-8"))
            select_text = archive.read("data/select.def").decode("utf-8-sig")
        except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("O manifesto ou o select.def do pacote Android não pôde ser lido.") from exc

        version = manifest.get("engine_version") if isinstance(manifest, dict) else None
        if not isinstance(version, str) or (expected_engine_version is not None and version != expected_engine_version):
            raise RuntimeError(
                f"O pacote de dados foi preparado para IKEMEN GO {version!r}, "
                f"mas a versão compatível esperada é {expected_engine_version!r}."
            )
        characters = manifest.get("characters") if isinstance(manifest, dict) else None
        declared_count = manifest.get("character_count") if isinstance(manifest, dict) else None
        if not isinstance(characters, list) or declared_count != len(characters):
            raise RuntimeError("A contagem de personagens declarada no manifesto não confere.")
        if expected_character_count is not None and len(characters) != expected_character_count:
            raise RuntimeError(
                f"O pacote Android declara {len(characters)} personagens; eram esperados "
                f"{expected_character_count}."
            )

        select_entries = _characters_section_entries(select_text)
        seen_definitions: set[str] = set()
        actual_series: Counter[str] = Counter()
        for character in characters:
            if not isinstance(character, dict):
                raise TypeError("O manifesto Android tem uma entrada de personagem inválida.")
            definition = character.get("definition_path")
            series = character.get("series")
            if not isinstance(definition, str) or not isinstance(series, str):
                raise TypeError("Uma entrada do manifesto não informa .def e série.")
            definition_path = _validate_member_name(definition)
            if len(definition_path.parts) < 2 or definition_path.parts[0] != "chars" or definition_path.suffix.casefold() != ".def":
                raise RuntimeError(f"Caminho .def fora de chars/: {definition!r}.")
            if definition not in exact_names:
                raise RuntimeError(f"Arquivo .def do manifesto ausente no pacote: {definition!r}.")
            relative_definition = "/".join(definition_path.parts[1:]).casefold()
            if relative_definition not in select_entries:
                raise RuntimeError(f"Personagem do manifesto não está registrado em data/select.def: {definition!r}.")
            if relative_definition in seen_definitions:
                raise RuntimeError(f"O manifesto repete a definição de personagem: {definition!r}.")
            seen_definitions.add(relative_definition)

            sprites = character.get("sprite_files")
            if not isinstance(sprites, list) or not sprites:
                raise RuntimeError(f"O personagem não declara arquivo .sff: {definition!r}.")
            valid_sprite = False
            for sprite in sprites:
                if not isinstance(sprite, str):
                    raise TypeError(f"Lista de .sff inválida em {definition!r}.")
                sprite_path = _validate_member_name(sprite)
                if (
                    len(sprite_path.parts) >= 3
                    and sprite_path.parts[0] == "chars"
                    and sprite_path.suffix.casefold() == ".sff"
                    and sprite in exact_names
                ):
                    valid_sprite = True
            if not valid_sprite:
                raise RuntimeError(f"Nenhum .sff registrado foi encontrado para {definition!r}.")
            actual_series[series] += 1

        if len(seen_definitions) != len(characters):
            raise RuntimeError("O manifesto não tem uma definição única por personagem.")
        declared_series = manifest.get("series_counts")
        if not isinstance(declared_series, dict) or declared_series != dict(actual_series):
            raise RuntimeError("A distribuição por série declarada no manifesto não confere.")
        shared_dependencies = manifest.get("shared_dependencies", [])
        if not isinstance(shared_dependencies, list):
            raise TypeError("A lista de dependências compartilhadas é inválida.")
        for dependency in shared_dependencies:
            if not isinstance(dependency, dict) or dependency.get("path") not in {"data/common1.cns"}:
                raise RuntimeError("O manifesto declara uma dependência compartilhada fora do escopo.")
            if dependency["path"] not in exact_names:
                raise RuntimeError(f"Dependência compartilhada ausente: {dependency['path']!r}.")

        return manifest


def copy_android_character_data_pack(
    download_dir: str | Path,
    progress: ProgressCallback | None = None,
    *,
    source_pack: str | Path | None = None,
    expected_sha256: str | None = None,
    expected_engine_version: str | None = DATA_PACK_ENGINE_VERSION,
    expected_character_count: int | None = DATA_PACK_CHARACTER_COUNT,
) -> Path:
    """Validate and atomically copy the bundled Android data ZIP beside the APK."""
    source = Path(source_pack).expanduser() if source_pack is not None else bundled_android_data_pack()
    expected_digest = (expected_sha256 or DATA_PACK_SHA256).casefold()
    if not re.fullmatch(r"[0-9a-f]{64}", expected_digest) or expected_digest == "0" * 64:
        raise RuntimeError("O SHA-256 esperado do pacote Android não foi configurado.")
    inspect_android_data_pack(
        source,
        expected_engine_version=expected_engine_version,
        expected_character_count=expected_character_count,
    )

    destination = Path(download_dir).expanduser()
    if destination.is_symlink():
        raise RuntimeError("A pasta de destino Android é um link simbólico; cópia cancelada.")
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / DATA_PACK_NAME
    if target.is_symlink() or (target.exists() and not target.is_file()):
        raise RuntimeError("O destino do pacote Android não é um arquivo normal; cópia cancelada.")
    if (
        target.is_file()
        and not target.is_symlink()
        and target.stat().st_size == source.stat().st_size
        and _sha256_file(target) == expected_digest
    ):
        if progress:
            progress("Pacote Android de personagens já está íntegro", 1, 1)
        return target

    temporary: Path | None = None
    try:
        digest = hashlib.sha256()
        total = source.stat().st_size
        copied = 0
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=destination, prefix=".jojo-android-data-", suffix=".tmp", delete=False
        ) as output, source.open("rb") as input_file:
            temporary = Path(output.name)
            if progress:
                progress("Copiando o pacote local de personagens Android", 0, total)
            while chunk := input_file.read(CHUNK_SIZE):
                copied += len(chunk)
                output.write(chunk)
                digest.update(chunk)
                if progress:
                    progress("Copiando o pacote local de personagens Android", copied, total)
            output.flush()
            os.fsync(output.fileno())
        if copied != total or digest.hexdigest() != expected_digest:
            raise RuntimeError("O SHA-256/tamanho do pacote de personagens Android não confere.")
        inspect_android_data_pack(
            temporary,
            expected_engine_version=expected_engine_version,
            expected_character_count=expected_character_count,
        )
        os.replace(temporary, target)
        temporary = None
    except OSError as exc:
        raise RuntimeError(f"Não consegui copiar o pacote Android: {exc}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    if progress:
        progress("Pacote de dados Android verificado e pronto", total, total)
    return target
