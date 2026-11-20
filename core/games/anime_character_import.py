"""Instala personagens MUGEN/IKEMEN incluídos no JoJo-OS ou fornecidos localmente.

Os botões de Naruto/Jujutsu provisionam os pacotes já presentes no instalador,
sem pedir que a pessoa procure, baixe ou extraia arquivos manualmente.
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path

SERIES: dict[str, tuple[str, str]] = {
    "naruto": ("Naruto", "Naruto"),
    "jujutsu_kaisen": ("Jujutsu Kaisen", "JujutsuKaisen"),
    "jojo": ("JoJo", "JoJo"),
    "dragon_ball": ("Dragon Ball Z", "DragonBallZ"),
    "one_piece": ("One Piece", "OnePiece"),
}
MAX_CHARACTER_FILES = 50_000
MAX_CHARACTER_BYTES = 1024 * 1024 * 1024


@dataclass(frozen=True)
class AnimeImportResult:
    game_dir: Path
    series: str
    folder_name: str
    character_entry: str
    character_dir: Path
    select_def: Path
    select_def_changed: bool


def _safe_slug(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", ascii_value).strip("_-")
    slug = re.sub(r"_+", "_", slug)[:56].strip("_-")
    if not slug:
        raise ValueError("O nome da pasta do personagem não contém caracteres seguros.")
    return slug


def _validate_source_tree(source: Path) -> tuple[Path, int]:
    if not source.is_dir():
        raise ValueError("Selecione a pasta extraída do personagem, não o arquivo ZIP.")
    root = source.resolve(strict=True)
    file_count = 0
    total_size = 0
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"A pasta do personagem contém link simbólico, não permitido: {path.name}")
        resolved = path.resolve(strict=True)
        if resolved != root and root not in resolved.parents:
            raise ValueError("A pasta do personagem contém um caminho que sai do diretório selecionado.")
        if path.is_file():
            file_count += 1
            total_size += path.stat().st_size
            if file_count > MAX_CHARACTER_FILES:
                raise ValueError("A pasta contém arquivos demais para importar com segurança.")
            if total_size > MAX_CHARACTER_BYTES:
                raise ValueError("O pacote do personagem ultrapassa o limite local de 1 GiB.")

    definitions = [
        path for path in root.iterdir()
        if path.is_file() and path.suffix.casefold() == ".def"
    ]
    if not definitions:
        raise ValueError("Não encontrei um arquivo .def na raiz da pasta. Selecione a pasta interna do personagem.")
    matching = [path for path in definitions if path.stem.casefold() == root.name.casefold()]
    if len(matching) == 1:
        definition = matching[0]
    elif len(definitions) == 1:
        definition = definitions[0]
    else:
        names = ", ".join(sorted(path.name for path in definitions))
        raise ValueError(f"A pasta tem vários arquivos .def ({names}); importe uma variante por vez.")

    has_sprites = any(
        path.is_file() and path.suffix.casefold() == ".sff"
        for path in root.rglob("*")
    )
    if not has_sprites:
        raise ValueError("Não encontrei nenhum arquivo .sff de sprites dentro da pasta.")
    return definition, total_size


def _entry_value(line: str) -> str:
    value = line.split(";", 1)[0].split(",", 1)[0].strip().replace("\\", "/")
    return value.casefold().strip("/")


def _write_select_entry(select_path: Path, entry: str, series_label: str) -> bool:
    created = not select_path.exists()
    newline = "\n"
    if created:
        text = "[Characters]\n"
    else:
        try:
            text = select_path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            text = select_path.read_text(encoding="cp1252")
        newline = "\r\n" if "\r\n" in text else "\n"

    lines = text.splitlines(keepends=True)
    section_index = next(
        (index for index, line in enumerate(lines) if line.strip().casefold() == "[characters]"),
        -1,
    )
    if section_index < 0:
        if lines and not lines[-1].endswith(("\n", "\r")):
            lines[-1] += newline
        lines.extend([newline, f"[Characters]{newline}"])
        section_index = len(lines) - 1

    section_end = len(lines)
    for index in range(section_index + 1, len(lines)):
        content = lines[index].strip()
        if content.startswith("[") and content.endswith("]"):
            section_end = index
            break

    entry_key = _entry_value(entry)
    for line in lines[section_index + 1:section_end]:
        current = _entry_value(line)
        if current == entry_key:
            return False

    if section_end > 0 and not lines[section_end - 1].endswith(("\n", "\r")):
        lines[section_end - 1] += newline
    lines[section_end:section_end] = [
        f"; JoJo-OS local import — {series_label}{newline}",
        f"{entry}{newline}",
    ]
    select_path.parent.mkdir(parents=True, exist_ok=True)

    if not created:
        backup = select_path.with_suffix(select_path.suffix + ".bak")
        if not backup.exists():
            backup.write_bytes(select_path.read_bytes())

    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", dir=select_path.parent,
            prefix=".select.", suffix=".tmp", delete=False,
        ) as temporary:
            temporary_name = temporary.name
            temporary.writelines(lines)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, select_path)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return True


def import_character_folder(
    game_dir: str | Path,
    series: str,
    source_dir: str | Path,
    *,
    permission_confirmed: bool = False,
) -> AnimeImportResult:
    """Copy one local character folder and register its explicit .def path.

    `permission_confirmed` represents the user's explicit acknowledgement in
    the UI; it is not a legal determination or a substitute for the creator's
    license/permission.
    """
    if not permission_confirmed:
        raise PermissionError("Confirme que você tem autorização para usar este pacote antes de importar.")
    series_key = series.strip().casefold().replace(" ", "_")
    if series_key not in SERIES:
        raise ValueError("Série não reconhecida. Escolha Naruto, Jujutsu Kaisen, JoJo, Dragon Ball Z ou One Piece.")
    series_label, folder_prefix = SERIES[series_key]

    root = Path(game_dir).expanduser().resolve()
    chars_dir = root / "chars"
    source = Path(source_dir).expanduser().resolve(strict=True)
    if not source.is_dir():
        raise ValueError("Selecione a pasta extraída do personagem.")
    if chars_dir.exists():
        chars_root = chars_dir.resolve()
        if source == chars_root or chars_root in source.parents:
            raise ValueError("Selecione a pasta original fora de chars/; o importador não copia a árvore do jogo para dentro dela.")

    definition, _total_size = _validate_source_tree(source)
    folder_name = f"{folder_prefix}_{_safe_slug(source.name)}"
    destination = chars_dir / folder_name
    if destination.exists():
        raise FileExistsError(
            f"Já existe {destination}. Nada foi sobrescrito; renomeie a pasta de origem ou remova o conflito manualmente."
        )

    chars_dir.mkdir(parents=True, exist_ok=True)
    staging_root = Path(tempfile.mkdtemp(prefix=".jojoos-anime-import-", dir=chars_dir))
    staged_character = staging_root / folder_name
    try:
        shutil.copytree(source, staged_character, symlinks=False, copy_function=shutil.copy2)
        staged_definition = staged_character / definition.name
        if not staged_definition.is_file():
            raise RuntimeError("O arquivo .def não foi copiado corretamente.")
        os.replace(staged_character, destination)
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)

    entry = f"{folder_name}/{definition.name}"
    select_path = root / "data" / "select.def"
    try:
        changed = _write_select_entry(select_path, entry, series_label)
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise

    return AnimeImportResult(
        game_dir=root,
        series=series_label,
        folder_name=folder_name,
        character_entry=entry,
        character_dir=destination,
        select_def=select_path,
        select_def_changed=changed,
    )


def register_existing_character(
    game_dir: str | Path,
    series: str,
    character_dir: str | Path,
) -> AnimeImportResult:
    """Validate one existing JoJo-OS-installed character and repair select.def."""
    series_key = series.strip().casefold().replace(" ", "_")
    if series_key not in SERIES:
        raise ValueError("Série não reconhecida.")
    series_label, folder_prefix = SERIES[series_key]
    root = Path(game_dir).expanduser().resolve()
    chars_dir = root / "chars"
    if chars_dir.is_symlink() or not chars_dir.is_dir():
        raise ValueError("A pasta chars/ não existe ou é um link simbólico.")
    supplied = Path(character_dir).expanduser()
    if supplied.is_symlink():
        raise ValueError("A pasta existente do personagem é um link simbólico.")
    character = supplied.resolve(strict=True)
    if character.parent != chars_dir.resolve(strict=True) or not character.is_dir():
        raise ValueError("A pasta do personagem precisa ser uma pasta direta e segura dentro de chars/.")
    if not character.name.casefold().startswith(f"{folder_prefix}_".casefold()):
        raise ValueError("A pasta existente não corresponde ao prefixo da série selecionada.")
    definition, _total_size = _validate_source_tree(character)
    entry = f"{character.name}/{definition.name}"
    select_path = root / "data" / "select.def"
    changed = _write_select_entry(select_path, entry, series_label)
    return AnimeImportResult(
        game_dir=root,
        series=series_label,
        folder_name=character.name,
        character_entry=entry,
        character_dir=character,
        select_def=select_path,
        select_def_changed=changed,
    )


BUNDLED_ASSETS_DIR = Path(__file__).with_name("character_assets")


def install_bundled_character_assets(
    game_dir: str | Path,
    series: str | None = None,
    folder_names: tuple[str, ...] | None = None,
    destination_names: dict[str, str] | None = None,
) -> tuple[AnimeImportResult, ...]:
    """Install included character folders and register explicit .def paths.

    Existing character folders are never overwritten. A valid existing folder with
    the same destination name is reused; an invalid collision is left untouched.
    `series` and `folder_names` can limit the operation to one series or character;
    `destination_names` maps included folders to canonical in-game directory names.
    """
    requested_label: str | None = None
    if series is not None:
        series_key = series.strip().casefold().replace(" ", "_")
        if series_key not in SERIES:
            raise ValueError("Série não reconhecida. Escolha Naruto, Jujutsu Kaisen, JoJo, Dragon Ball Z ou One Piece.")
        requested_label = SERIES[series_key][0]
    requested_folders = {name.casefold() for name in folder_names} if folder_names is not None else None
    destination_names = destination_names or {}

    game_root = Path(game_dir).expanduser().resolve()
    chars_dir = game_root / "chars"
    select_path = game_root / "data" / "select.def"
    if not BUNDLED_ASSETS_DIR.is_dir():
        return ()
    chars_dir.mkdir(parents=True, exist_ok=True)
    results: list[AnimeImportResult] = []

    for source in sorted(BUNDLED_ASSETS_DIR.iterdir(), key=lambda item: item.name.casefold()):
        if source.is_symlink() or not source.is_dir():
            continue
        folded_name = source.name.casefold()
        if folded_name.startswith("naruto_"):
            series_label = "Naruto"
        elif folded_name.startswith("jujutsukaisen_"):
            series_label = "Jujutsu Kaisen"
        elif folded_name.startswith("jojo_"):
            series_label = "JoJo"
        elif folded_name.startswith("dragonballz_"):
            series_label = "Dragon Ball Z"
        elif folded_name.startswith("onepiece_"):
            series_label = "One Piece"
        else:
            continue
        if requested_label is not None and series_label != requested_label:
            continue
        if requested_folders is not None and folded_name not in requested_folders:
            continue
        if _safe_slug(source.name) != source.name:
            raise ValueError(f"Nome inseguro para personagem empacotado: {source.name!r}")
        destination_name = destination_names.get(source.name, source.name)
        if _safe_slug(destination_name) != destination_name:
            raise ValueError(f"Nome inseguro para pasta de destino: {destination_name!r}")
        _source_definition, _ = _validate_source_tree(source)

        existing = next(
            (child for child in chars_dir.iterdir() if child.name.casefold() == destination_name.casefold()),
            None,
        )
        if existing is None:
            staging_root = Path(tempfile.mkdtemp(prefix=".jojoos-bundled-", dir=chars_dir))
            staged_character = staging_root / destination_name
            try:
                shutil.copytree(source, staged_character, symlinks=False, copy_function=shutil.copy2)
                staged_definition, _ = _validate_source_tree(staged_character)
                destination = chars_dir / destination_name
                os.replace(staged_character, destination)
                definition_name = staged_definition.name
            finally:
                shutil.rmtree(staging_root, ignore_errors=True)
        else:
            if existing.is_symlink() or not existing.is_dir():
                continue
            try:
                existing_definition, _ = _validate_source_tree(existing)
            except ValueError:
                continue
            destination = existing
            definition_name = existing_definition.name

        entry = f"{destination.name}/{definition_name}"
        changed = _write_select_entry(select_path, entry, series_label)
        results.append(
            AnimeImportResult(
                game_dir=game_root,
                series=series_label,
                folder_name=destination.name,
                character_entry=entry,
                character_dir=destination,
                select_def=select_path,
                select_def_changed=changed,
            )
        )
    return tuple(results)
