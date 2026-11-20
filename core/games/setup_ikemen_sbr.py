"""Prepara pastas SBR do IKEMEN GO sem fingir que os personagens estão instalados.

Use: python setup_ikemen_sbr.py [--game-dir CAMINHO_DO_IKEMEN]

A versão original anexada usava o diretório de trabalho atual e criava arquivos
.def de exemplo. Isso podia alterar a pasta errada e fazer personagens vazios
parecerem instalados. Esta versão ancora o padrão ao diretório do script, cria
pastas preparadas e só registra um personagem quando encontra .def e .sff reais.
"""
from __future__ import annotations

import argparse
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

SBR_CHARACTERS: dict[str, tuple[str, ...]] = {
    "Johnny_Joestar": ("johnny_joestar", "johnny joestar", "johnny"),
    "Gyro_Zeppeli": ("gyro_zeppeli", "gyro zeppeli", "gyro"),
    "Diego_Brando": ("diego_brando", "diego brando", "diego"),
    "Funny_Valentine": ("funny_valentine", "funny valentine", "valentine"),
}

# These two real packages were supplied in the user's IKEMEN archive. The keys
# are bundled source folders; values are the folder names recognized by SBR.
SBR_BUNDLED_FOLDER_MAP: dict[str, str] = {
    "JoJo_Diego_Brando": "Diego_Brando",
    "JoJo_Funny_Valentine": "Funny_Valentine",
}

INSTALL_NOTE = (
    "Pasta preparada pelo JoJo-OS.\n"
    "Coloque aqui os arquivos reais do personagem obtidos legalmente de seu autor,\n"
    "incluindo o .def e os arquivos que ele referencia (por exemplo .sff, .air,\n"
    ".cmd, .cns/.zss e .snd). Não substitua arquivos do IKEMEN GO.\n"
    "Depois execute python setup_ikemen_sbr.py novamente para registrar o personagem.\n"
)


@dataclass(frozen=True)
class SetupResult:
    game_dir: Path
    created_directories: tuple[str, ...]
    registered: tuple[str, ...]
    waiting_for_assets: tuple[str, ...]
    select_def_changed: bool


def _normalize_name(value: str) -> str:
    return "".join(character.casefold() for character in value if character.isalnum())


def _has_real_character_files(directory: Path) -> bool:
    """Require a definition and sprite archive directly in the char folder."""
    if not directory.is_dir():
        return False
    files = [path for path in directory.iterdir() if path.is_file()]
    has_definition = any(path.suffix.casefold() == ".def" for path in files)
    has_sprite_archive = any(path.suffix.casefold() == ".sff" for path in files)
    return has_definition and has_sprite_archive


def _find_sbr_folders(chars_dir: Path) -> dict[str, Path]:
    folders = [path for path in chars_dir.iterdir() if path.is_dir()]
    found: dict[str, Path] = {}
    for canonical, aliases in SBR_CHARACTERS.items():
        allowed = {_normalize_name(canonical), *(_normalize_name(alias) for alias in aliases)}
        candidates = [
            folder for folder in folders
            if _normalize_name(folder.name) in allowed and _has_real_character_files(folder)
        ]
        if candidates:
            candidates.sort(key=lambda folder: (folder.name.casefold() != canonical.casefold(), folder.name.casefold()))
            found[canonical] = candidates[0]
    return found


def _character_entry_key(entry: str) -> set[str]:
    value = entry.split(";", 1)[0].split(",", 1)[0].strip().replace("\\", "/")
    if not value:
        return set()
    path = PurePosixPath(value)
    keys = {_normalize_name(part) for part in path.parts if part not in {".", ".."}}
    if path.suffix.casefold() == ".def":
        keys.add(_normalize_name(path.stem))
    return keys


def _update_select_def(select_path: Path, chars_dir: Path, folders: dict[str, Path]) -> tuple[tuple[str, ...], bool]:
    created = not select_path.exists()
    section_created = False
    newline = "\n"
    if created:
        text = "[ExtraStages]\n\n[Characters]\n"
    else:
        try:
            text = select_path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            text = select_path.read_text(encoding="cp1252")
        newline = "\r\n" if "\r\n" in text else "\n"

    lines = text.splitlines(keepends=True)
    characters_index = next(
        (index for index, line in enumerate(lines) if line.strip().casefold() == "[characters]"),
        -1,
    )
    if characters_index < 0:
        if lines and not lines[-1].endswith(("\n", "\r")):
            lines[-1] += newline
        lines.extend([newline, f"[Characters]{newline}"])
        characters_index = len(lines) - 1
        section_created = True

    section_end = len(lines)
    for index in range(characters_index + 1, len(lines)):
        content = lines[index].strip()
        if content.startswith("[") and content.endswith("]"):
            section_end = index
            break

    existing_keys: set[str] = set()
    for line in lines[characters_index + 1:section_end]:
        existing_keys.update(_character_entry_key(line))

    to_add: list[str] = []
    registered: list[str] = []
    for canonical in SBR_CHARACTERS:
        folder = folders.get(canonical)
        if folder is None:
            continue
        relative_name = folder.relative_to(chars_dir).as_posix()
        folder_key = _normalize_name(folder.name)
        registered.append(relative_name)
        if folder_key not in existing_keys:
            to_add.append(relative_name + newline)
            existing_keys.add(folder_key)

    if not to_add and not (created or section_created):
        return tuple(registered), False

    if section_end > 0 and not lines[section_end - 1].endswith(("\n", "\r")):
        lines[section_end - 1] += newline
    lines[section_end:section_end] = to_add
    select_path.parent.mkdir(parents=True, exist_ok=True)

    if not created:
        backup_path = select_path.with_suffix(select_path.suffix + ".bak")
        if not backup_path.exists():
            backup_path.write_bytes(select_path.read_bytes())

    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", dir=select_path.parent,
            prefix=".select.", suffix=".tmp", delete=False,
        ) as temporary:
            temp_name = temporary.name
            temporary.writelines(lines)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temp_name, select_path)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)
    return tuple(registered), True


def setup_game(game_dir: str | Path | None = None) -> SetupResult:
    """Create the SBR folder layout and register only complete local characters."""
    root = Path(game_dir).expanduser().resolve() if game_dir is not None else Path(__file__).resolve().parent
    root.mkdir(parents=True, exist_ok=True)
    chars_dir = root / "chars"
    data_dir = root / "data"
    chars_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    created: list[str] = []
    for character in SBR_CHARACTERS:
        folder = chars_dir / character
        if not folder.exists():
            folder.mkdir(parents=True)
            created.append(character)
        note = folder / "LEIA_ANTES_DE_INSTALAR.txt"
        if not note.exists():
            note.write_text(INSTALL_NOTE, encoding="utf-8")

    real_folders = _find_sbr_folders(chars_dir)
    registered, changed = _update_select_def(data_dir / "select.def", chars_dir, real_folders)
    waiting = tuple(character for character in SBR_CHARACTERS if character not in real_folders)
    return SetupResult(
        game_dir=root,
        created_directories=tuple(created),
        registered=registered,
        waiting_for_assets=waiting,
        select_def_changed=changed,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepara pastas de personagens SBR no IKEMEN GO.")
    parser.add_argument(
        "--game-dir", type=Path, default=None,
        help="pasta do IKEMEN GO; sem esta opção, usa a pasta deste script",
    )
    args = parser.parse_args()
    result = setup_game(args.game_dir)
    print(f"Pasta do IKEMEN GO: {result.game_dir}")
    print("Estrutura chars/ e data/ pronta.")
    if result.created_directories:
        print("Pastas preparadas: " + ", ".join(result.created_directories))
    if result.registered:
        print("Personagens reais registrados em data/select.def: " + ", ".join(result.registered))
    else:
        print("Nenhum personagem SBR foi registrado: coloque arquivos .def e .sff reais nas pastas chars/<personagem>/ e execute este script de novo.")
    if result.waiting_for_assets:
        print("Aguardando assets autorizados para: " + ", ".join(result.waiting_for_assets))
    if result.select_def_changed:
        print("select.def atualizado. Foi preservada uma cópia .bak quando já existia.")
    else:
        print("select.def já estava atualizado; nada foi sobrescrito.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
