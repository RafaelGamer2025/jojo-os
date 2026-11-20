"""Instalador seguro e launcher do IKEMEN GO para o JoJo-OS.

O executável oficial não é embutido no JoJo-OS. Se estiver faltando, a
instalação consulta a última release estável do repositório oficial, escolhe o
ZIP da plataforma, valida o SHA-256 publicado e só então o extrai.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from core.games.anime_character_import import install_bundled_character_assets
from core.games.setup_ikemen_sbr import SBR_BUNDLED_FOLDER_MAP, SetupResult, setup_game

OFFICIAL_REPOSITORY = "ikemen-engine/Ikemen-GO"
LATEST_RELEASE_API = "https://api.github.com/repos/ikemen-engine/Ikemen-GO/releases/latest"
OFFICIAL_RELEASE_PREFIX = "https://github.com/ikemen-engine/Ikemen-GO/releases/download/"
MAX_DOWNLOAD_BYTES = 250 * 1024 * 1024
MAX_UNPACKED_BYTES = 1024 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 30_000
CHUNK_SIZE = 256 * 1024

ProgressCallback = Callable[[str, int, int], None]


@dataclass(frozen=True)
class IkemenInstallResult:
    game_dir: Path
    executable: Path
    version: str | None
    downloaded: bool
    setup_result: SetupResult | None
    bundled_characters: tuple[str, ...] = ()


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_install_dir() -> Path:
    """Keep downloaded game files beside the JoJo-OS source and user data."""
    return project_root() / "games" / "ikemen_go"


def _install_bundled_sbr_characters(game_dir: str | Path):
    return install_bundled_character_assets(
        game_dir,
        series="jojo",
        folder_names=tuple(SBR_BUNDLED_FOLDER_MAP),
        destination_names=SBR_BUNDLED_FOLDER_MAP,
    )


def legacy_install_dir() -> Path:
    """Support an older manual install path without moving user files."""
    return Path(__file__).resolve().parent / "jojo_ikemen"


def _platform_key(platform_key: str | None = None) -> str:
    value = (platform_key or sys.platform).casefold()
    machine = platform.machine().casefold()
    if value in {"win32", "windows", "win"}:
        if struct.calcsize("P") < 8:
            raise RuntimeError("O IKEMEN GO atual exige Windows de 64 bits; este Python é de 32 bits.")
        return "windows"
    if value in {"linux", "linux2"}:
        if machine not in {"x86_64", "amd64"}:
            raise RuntimeError("A release Linux oficial disponível exige arquitetura x86-64.")
        return "linux"
    if value in {"darwin", "macos", "mac"}:
        if machine not in {"arm64", "aarch64"}:
            raise RuntimeError("A release macOS oficial disponível é para Apple Silicon (arm64).")
        return "macos"
    raise RuntimeError(f"A release oficial não oferece um pacote compatível com a plataforma {value!r}.")


def executable_name(platform_key: str | None = None) -> str:
    key = _platform_key(platform_key)
    return {"windows": "Ikemen_GO.exe", "linux": "Ikemen_GO", "macos": "Ikemen_GO.command"}[key]


def _is_usable_executable(path: Path, platform_key: str | None = None) -> bool:
    if not path.is_file():
        return False
    if _platform_key(platform_key) == "linux":
        return os.access(path, os.X_OK)
    return True


def _is_complete_game_installation(root: Path, platform_key: str | None = None) -> bool:
    executable = root / executable_name(platform_key)
    chars = root / "chars"
    select_def = root / "data" / "select.def"
    return (
        _is_usable_executable(executable, platform_key)
        and not chars.is_symlink()
        and chars.is_dir()
        and not select_def.is_symlink()
        and select_def.is_file()
    )


def find_installed_game_dir(platform_key: str | None = None) -> Path | None:
    for candidate in (default_install_dir(), legacy_install_dir()):
        if _is_complete_game_installation(candidate, platform_key):
            return candidate
    return None


def get_game_executable(game_dir: str | Path | None = None, platform_key: str | None = None) -> Path:
    root = Path(game_dir).expanduser().resolve() if game_dir is not None else find_installed_game_dir(platform_key)
    if root is None:
        root = default_install_dir()
    return root / executable_name(platform_key)


def _request(url: str, *, accept: str = "application/vnd.github+json") -> urllib.request.Request:
    return urllib.request.Request(
        url,
        headers={
            "User-Agent": "JoJo-OS-IKEMEN-Installer/1.0",
            "Accept": accept,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )


def _open_url_with_retry(request, *, timeout: int):
    """Retry short-lived transport errors; respect explicit, short Retry-After values."""
    attempts = 3
    for attempt in range(attempts):
        try:
            return urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            delay = 0
            if exc.code == 429:
                retry_after = exc.headers.get("Retry-After", "")
                if attempt < attempts - 1 and retry_after.isdigit() and 0 < int(retry_after) <= 15:
                    delay = int(retry_after)
                else:
                    raise
            elif exc.code in {408, 500, 502, 503, 504} and attempt < attempts - 1:
                delay = min(2 ** attempt, 4)
            else:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt >= attempts - 1:
                raise
            delay = min(2 ** attempt, 4)
        time.sleep(delay)
    raise RuntimeError("O GitHub não retornou uma resposta válida depois das tentativas limitadas.")


def _read_small_url(url: str, max_bytes: int = 2 * 1024 * 1024) -> bytes:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {"api.github.com", "github.com"}:
        raise RuntimeError("O instalador recusou uma URL fora do GitHub oficial.")
    with _open_url_with_retry(_request(url), timeout=30) as response:
        final_host = urllib.parse.urlparse(response.geturl()).hostname
        if final_host not in {"api.github.com", "github.com", "release-assets.githubusercontent.com"}:
            raise RuntimeError("O GitHub redirecionou a consulta para um host inesperado.")
        data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise RuntimeError("A resposta do GitHub ultrapassou o limite esperado.")
    return data


def get_latest_stable_release() -> dict:
    try:
        release = json.loads(_read_small_url(LATEST_RELEASE_API).decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError(f"Não consegui consultar as releases oficiais do GitHub: {exc}") from exc
    if release.get("draft") or release.get("prerelease"):
        raise RuntimeError("O endpoint do GitHub não retornou uma release estável válida.")
    tag = release.get("tag_name")
    assets = release.get("assets")
    if not isinstance(tag, str) or not re.fullmatch(r"v?[0-9A-Za-z._-]+", tag) or not isinstance(assets, list):
        raise RuntimeError("A resposta do GitHub não tem o formato de release esperado.")
    return release


def select_platform_asset(release: dict, platform_key: str | None = None) -> dict:
    key = _platform_key(platform_key)
    tag = release.get("tag_name")
    expected_name = f"Ikemen_GO-{tag}-{key}.zip"
    for asset in release.get("assets", []):
        if not isinstance(asset, dict) or asset.get("name") != expected_name:
            continue
        url = asset.get("browser_download_url")
        if not isinstance(url, str) or not url.startswith(OFFICIAL_RELEASE_PREFIX):
            raise RuntimeError("O asset não aponta para a página oficial de releases do projeto.")
        if not url.endswith("/" + expected_name):
            raise RuntimeError("O nome do asset não corresponde à plataforma solicitada.")
        return asset
    raise RuntimeError(f"Não há o pacote oficial {expected_name} nesta release.")


def select_android_asset(release: dict) -> dict:
    """Select the official Android archive without treating it as a desktop game."""
    tag = release.get("tag_name")
    if not isinstance(tag, str) or not re.fullmatch(r"v?[0-9A-Za-z._-]+", tag):
        raise RuntimeError("A release não tem uma versão Android segura.")
    expected_name = f"Ikemen_GO-{tag}-android.zip"
    for asset in release.get("assets", []):
        if not isinstance(asset, dict) or asset.get("name") != expected_name:
            continue
        url = asset.get("browser_download_url")
        if not isinstance(url, str) or not url.startswith(OFFICIAL_RELEASE_PREFIX):
            raise RuntimeError("O pacote Android não aponta para a release oficial.")
        if not url.endswith("/" + expected_name):
            raise RuntimeError("O nome do pacote Android não corresponde à release.")
        return asset
    raise RuntimeError(f"A release oficial não contém o pacote Android {expected_name}.")


def _published_sha256(release: dict, asset: dict) -> str:
    digest = asset.get("digest")
    if isinstance(digest, str) and digest.startswith("sha256:"):
        value = digest.split(":", 1)[1].casefold()
        if re.fullmatch(r"[0-9a-f]{64}", value):
            return value

    sums_asset = next(
        (item for item in release.get("assets", []) if isinstance(item, dict) and item.get("name") == "SHA256SUMS.txt"),
        None,
    )
    if sums_asset and isinstance(sums_asset.get("browser_download_url"), str):
        url = sums_asset["browser_download_url"]
        if not url.startswith(OFFICIAL_RELEASE_PREFIX):
            raise RuntimeError("O checksum não aponta para a release oficial.")
        sums_text = _read_small_url(url, max_bytes=1024 * 1024).decode("utf-8", errors="replace")
        escaped_name = re.escape(str(asset.get("name", "")))
        match = re.search(rf"^([0-9a-fA-F]{{64}})\s+\*?{escaped_name}\s*$", sums_text, re.MULTILINE)
        if match:
            return match.group(1).casefold()
    raise RuntimeError("A release não publica um SHA-256 verificável para este pacote; download cancelado.")


def _download_asset(asset: dict, destination: Path, expected_sha256: str, progress: ProgressCallback | None = None) -> None:
    url = str(asset["browser_download_url"])
    if not url.startswith(OFFICIAL_RELEASE_PREFIX):
        raise RuntimeError("O instalador recusou um link de download que não é oficial.")
    expected_size = int(asset.get("size") or 0)
    if expected_size <= 0 or expected_size > MAX_DOWNLOAD_BYTES:
        raise RuntimeError("O tamanho anunciado do pacote é inválido ou excede o limite de 250 MiB.")

    digest = hashlib.sha256()
    downloaded = 0
    request = _request(url, accept="application/octet-stream")
    with _open_url_with_retry(request, timeout=60) as response, destination.open("wb") as output:
        final_host = urllib.parse.urlparse(response.geturl()).hostname
        if final_host not in {"github.com", "release-assets.githubusercontent.com"}:
            raise RuntimeError("O download foi redirecionado para um host inesperado.")
        length_header = response.headers.get("Content-Length")
        total = int(length_header) if length_header and length_header.isdigit() else expected_size
        if total > MAX_DOWNLOAD_BYTES:
            raise RuntimeError("O pacote excede o limite de download de 250 MiB.")
        if progress:
            progress("Baixando o pacote oficial do IKEMEN GO", 0, total)
        while True:
            chunk = response.read(CHUNK_SIZE)
            if not chunk:
                break
            downloaded += len(chunk)
            if downloaded > MAX_DOWNLOAD_BYTES or downloaded > expected_size:
                raise RuntimeError("O download ultrapassou o tamanho anunciado pelo GitHub.")
            output.write(chunk)
            digest.update(chunk)
            if progress:
                progress("Baixando o pacote oficial do IKEMEN GO", downloaded, total)
        output.flush()
        os.fsync(output.fileno())

    if downloaded != expected_size:
        raise RuntimeError(f"Download incompleto: esperava {expected_size} bytes e recebi {downloaded}.")
    if digest.hexdigest() != expected_sha256:
        raise RuntimeError("O SHA-256 do pacote não confere com o checksum publicado pelo GitHub.")


def _safe_extract(zip_path: Path, destination: Path, progress: ProgressCallback | None = None) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with zipfile.ZipFile(zip_path) as archive:
        infos = archive.infolist()
        if len(infos) > MAX_ARCHIVE_ENTRIES:
            raise RuntimeError("O ZIP tem quantidade excessiva de arquivos e foi recusado.")
        uncompressed = sum(info.file_size for info in infos)
        if uncompressed > MAX_UNPACKED_BYTES:
            raise RuntimeError("O conteúdo descompactado excede 1 GiB e foi recusado.")
        bad_member = archive.testzip()
        if bad_member:
            raise RuntimeError(f"CRC inválido no arquivo do pacote: {bad_member}.")

        for index, info in enumerate(infos, start=1):
            normalized = info.filename.replace("\\", "/")
            posix = PurePosixPath(normalized)
            windows = PureWindowsPath(normalized)
            if posix.is_absolute() or windows.is_absolute() or windows.drive or any(part in {"..", ""} for part in posix.parts):
                raise RuntimeError(f"O ZIP contém um caminho inseguro: {info.filename!r}.")
            if not posix.parts or any("\x00" in part for part in posix.parts):
                raise RuntimeError(f"O ZIP contém um nome de arquivo inválido: {info.filename!r}.")

            target = destination.joinpath(*posix.parts)
            resolved = target.resolve()
            if resolved != root and root not in resolved.parents:
                raise RuntimeError(f"O ZIP tenta gravar fora da pasta de instalação: {info.filename!r}.")
            mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(mode):
                raise RuntimeError(f"O ZIP contém um link simbólico não permitido: {info.filename!r}.")
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    raise RuntimeError(f"O ZIP tem caminhos duplicados: {info.filename!r}.")
                with archive.open(info, "r") as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output, length=CHUNK_SIZE)
                permissions = mode & 0o777
                if permissions:
                    try:
                        target.chmod(permissions)
                    except OSError:
                        pass
            if progress and index % 20 == 0:
                progress("Extraindo arquivos do IKEMEN GO", index, len(infos))
        if progress:
            progress("Extração concluída", len(infos), len(infos))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _is_valid_android_apk(path: Path) -> bool:
    if not path.is_file() or path.is_symlink():
        return False
    try:
        with zipfile.ZipFile(path) as apk:
            return "AndroidManifest.xml" in apk.namelist() and apk.testzip() is None
    except (OSError, zipfile.BadZipFile):
        return False


def _write_android_archive_member(archive: zipfile.ZipFile, info: zipfile.ZipInfo, target: Path) -> None:
    mode = (info.external_attr >> 16) & 0xFFFF
    if stat.S_ISLNK(mode):
        raise RuntimeError(f"O pacote Android contém link simbólico não permitido: {info.filename!r}.")
    if target.is_symlink():
        raise RuntimeError(f"O destino Android é um link simbólico: {target.name}.")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=target.parent, prefix=f".{target.name}-", suffix=".tmp", delete=False
        ) as output:
            temporary = Path(output.name)
            with archive.open(info, "r") as source:
                copied = 0
                while chunk := source.read(CHUNK_SIZE):
                    copied += len(chunk)
                    if copied > info.file_size or copied > MAX_DOWNLOAD_BYTES:
                        raise RuntimeError("Um arquivo do pacote Android excedeu o tamanho seguro.")
                    output.write(chunk)
            if copied != info.file_size:
                raise RuntimeError("Um arquivo do pacote Android está incompleto.")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, target)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _extract_android_apk(
    archive_path: Path,
    destination: Path,
    version: str,
    archive_sha256: str,
) -> Path:
    if destination.is_symlink():
        raise RuntimeError("A pasta de destino Android é um link simbólico; download cancelado.")
    destination.mkdir(parents=True, exist_ok=True)
    try:
        archive = zipfile.ZipFile(archive_path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise RuntimeError("O pacote Android oficial não é um ZIP íntegro.") from exc

    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_ARCHIVE_ENTRIES or sum(info.file_size for info in infos) > MAX_UNPACKED_BYTES:
            raise RuntimeError("O pacote Android excede os limites seguros de arquivos/tamanho.")
        for info in infos:
            normalized = info.filename.replace("\\", "/")
            posix = PurePosixPath(normalized)
            windows = PureWindowsPath(normalized)
            if (
                posix.is_absolute()
                or windows.is_absolute()
                or windows.drive
                or not posix.parts
                or any(part in {"", ".", ".."} for part in posix.parts)
            ):
                raise RuntimeError(f"O ZIP Android contém um caminho inseguro: {info.filename!r}.")
            if stat.S_ISLNK((info.external_attr >> 16) & 0xFFFF):
                raise RuntimeError(f"O ZIP Android contém link simbólico: {info.filename!r}.")
        bad_member = archive.testzip()
        if bad_member:
            raise RuntimeError(f"CRC inválido no ZIP Android: {bad_member}.")

        apk_infos = [info for info in infos if PurePosixPath(info.filename).name.casefold() == "ikemen-go.apk"]
        if len(apk_infos) != 1:
            raise RuntimeError("O pacote Android não contém exatamente um arquivo ikemen-go.apk.")
        apk_info = apk_infos[0]
        if apk_info.file_size <= 0 or apk_info.file_size > MAX_DOWNLOAD_BYTES:
            raise RuntimeError("O tamanho do APK Android é inválido ou excede o limite seguro.")

        apk_path = destination / "ikemen-go.apk"
        if apk_path.is_symlink() or (apk_path.exists() and not apk_path.is_file()):
            raise RuntimeError("O destino do APK Android não é um arquivo normal; download cancelado.")
        metadata_path = destination / "download-info.json"
        if metadata_path.is_symlink() or (metadata_path.exists() and not metadata_path.is_file()):
            raise RuntimeError("O destino dos metadados Android não é um arquivo normal; download cancelado.")

        staged_apk: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=destination, prefix=".ikemen-go-apk-", suffix=".tmp", delete=False
            ) as staged:
                staged_apk = Path(staged.name)
            _write_android_archive_member(archive, apk_info, staged_apk)
            if not _is_valid_android_apk(staged_apk):
                raise RuntimeError("O arquivo extraído não é um APK válido com AndroidManifest.xml.")

            for support_name in ("README.md", "LICENSES.txt"):
                support = [info for info in infos if info.filename.casefold() == support_name.casefold()]
                support_path = destination / support_name
                if support_path.is_symlink():
                    raise RuntimeError(f"O arquivo auxiliar Android {support_name} é um link simbólico.")
                if len(support) == 1 and support[0].file_size <= 2 * 1024 * 1024:
                    _write_android_archive_member(archive, support[0], support_path)

            os.replace(staged_apk, apk_path)
            staged_apk = None
        finally:
            if staged_apk is not None:
                staged_apk.unlink(missing_ok=True)

    metadata = {
        "version": version,
        "asset": f"Ikemen_GO-{version}-android.zip",
        "archive_sha256": archive_sha256,
        "apk_sha256": _sha256_file(apk_path),
    }
    metadata_path = destination / "download-info.json"
    if metadata_path.is_symlink():
        raise RuntimeError("O arquivo de metadados Android é um link simbólico; download cancelado.")
    temporary_metadata: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destination, prefix=".download-info-", suffix=".tmp", delete=False
        ) as output:
            temporary_metadata = Path(output.name)
            json.dump(metadata, output, ensure_ascii=False, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_metadata, metadata_path)
        temporary_metadata = None
    finally:
        if temporary_metadata is not None:
            temporary_metadata.unlink(missing_ok=True)
    return apk_path


def download_android_ikemen(
    download_dir: str | Path | None = None,
    progress: ProgressCallback | None = None,
) -> Path:
    """Download the official Android release and extract only its installable APK."""
    release = get_latest_stable_release()
    asset = select_android_asset(release)
    checksum = _published_sha256(release, asset)
    version = str(release["tag_name"])
    safe_version = re.sub(r"[^A-Za-z0-9._-]", "_", version)
    destination = (
        Path(download_dir).expanduser()
        if download_dir is not None
        else Path.home() / "Downloads" / "JoJo-OS" / "IKEMEN-Android" / safe_version
    )
    if destination.is_symlink():
        raise RuntimeError("A pasta de download Android é um link simbólico; download cancelado.")
    destination.mkdir(parents=True, exist_ok=True)
    apk_path = destination / "ikemen-go.apk"
    metadata_path = destination / "download-info.json"
    if apk_path.is_file() and not apk_path.is_symlink() and metadata_path.is_file() and not metadata_path.is_symlink():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            metadata = {}
        if (
            isinstance(metadata, dict)
            and metadata.get("version") == version
            and metadata.get("archive_sha256") == checksum
            and metadata.get("apk_sha256") == _sha256_file(apk_path)
            and _is_valid_android_apk(apk_path)
        ):
            if progress:
                progress("APK Android oficial já baixado e íntegro", 1, 1)
            return apk_path

    if progress:
        progress(f"Baixando IKEMEN GO Android {version} da release oficial", 0, int(asset.get("size") or 0))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".ikemen-android-", dir=destination.parent) as temporary_name:
        archive_path = Path(temporary_name) / "ikemen-android.zip"
        _download_asset(asset, archive_path, checksum, progress)
        apk_path = _extract_android_apk(archive_path, destination, version, checksum)
    if progress:
        progress("APK Android verificado e pronto para transferir ao celular", 1, 1)
    return apk_path


def _find_extracted_game_root(extracted_dir: Path, platform_key: str) -> Path:
    wanted = executable_name(platform_key).casefold()
    candidates = [path.parent for path in extracted_dir.rglob("*") if path.is_file() and path.name.casefold() == wanted]
    valid = [path for path in candidates if (path / "data" / "select.def").is_file() and (path / "chars").is_dir()]
    if len(valid) != 1:
        raise RuntimeError("O ZIP oficial não contém uma única instalação válida com executável, chars/ e data/select.def.")
    return valid[0]


def _merge_missing_files(source: Path, destination: Path) -> None:
    """Repair an incomplete install without overwriting local characters/settings."""
    if destination.is_symlink():
        raise RuntimeError("A pasta de instalação é um link simbólico; reparo cancelado.")
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    for path in source.rglob("*"):
        relative = path.relative_to(source)
        target = destination / relative
        current = destination
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise RuntimeError(f"O reparo encontrou um link simbólico: {relative}.")
        resolved = target.resolve()
        if resolved != root and root not in resolved.parents:
            raise RuntimeError(f"O reparo tentou sair da instalação: {relative}.")
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def _replace_root_runtime_files(source: Path, destination: Path, platform_key: str) -> None:
    runtime_suffixes = {".dll", ".so", ".dylib", ".command"}
    executable = executable_name(platform_key).casefold()
    for path in source.iterdir():
        if not path.is_file() or (path.name.casefold() != executable and path.suffix.casefold() not in runtime_suffixes):
            continue
        target = destination / path.name
        if target.is_symlink():
            raise RuntimeError(f"O runtime existente é um link simbólico: {path.name}.")
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=destination, prefix=f".{path.name}-", suffix=".tmp", delete=False
            ) as output:
                temporary = Path(output.name)
                with path.open("rb") as source_file:
                    shutil.copyfileobj(source_file, output, length=CHUNK_SIZE)
                output.flush()
                os.fsync(output.fileno())
            shutil.copystat(path, temporary)
            os.replace(temporary, target)
            temporary = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def configurar_tela_cheia(game_dir: str | Path) -> Path:
    """Set the official IKEMEN [Video] Fullscreen option and preserve a backup."""
    root = Path(game_dir).expanduser().resolve()
    config_path = root / "save" / "config.ini"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if config_path.is_symlink():
        raise RuntimeError("O arquivo save/config.ini é um link simbólico; por segurança não foi alterado.")

    existed = config_path.exists()
    if existed:
        if not config_path.is_file() or config_path.stat().st_size > 2 * 1024 * 1024:
            raise RuntimeError("O arquivo save/config.ini não é um arquivo INI válido ou excede 2 MiB.")
        try:
            original = config_path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            original = config_path.read_text(encoding="cp1252")
    else:
        original = ""

    lines = original.splitlines(keepends=True)
    section = ""
    video_start: int | None = None
    video_end: int | None = None
    fullscreen_lines: list[int] = []
    for index, line in enumerate(lines):
        stripped = line.split(";", 1)[0].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if section == "video" and video_end is None:
                video_end = index
            section = stripped[1:-1].strip().casefold()
            if section == "video" and video_start is None:
                video_start = index
        elif section == "video" and re.match(r"^\s*fullscreen\s*=", stripped, re.IGNORECASE):
            fullscreen_lines.append(index)
    if section == "video" and video_end is None:
        video_end = len(lines)

    changed = False
    if video_start is None:
        if lines and not lines[-1].endswith(("\n", "\r")):
            lines[-1] += "\n"
        if lines and lines[-1].strip():
            lines.append("\n")
        lines.extend(["[Video]\n", "Fullscreen = 1\n"])
        changed = True
    elif fullscreen_lines:
        for index in fullscreen_lines:
            line = lines[index]
            ending = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
            body = line[:-len(ending)] if ending else line
            key, _equals, value = body.partition("=")
            comment = ""
            if ";" in value:
                comment = " ;" + value.split(";", 1)[1].lstrip()
            replacement = f"{key.rstrip()} = 1{comment}{ending}"
            if replacement != line:
                lines[index] = replacement
                changed = True
    else:
        insert_at = video_end if video_end is not None else len(lines)
        newline = "\r\n" if any(line.endswith("\r\n") for line in lines) else "\n"
        lines.insert(insert_at, f"Fullscreen = 1{newline}")
        changed = True

    if not changed:
        return config_path

    if existed:
        backup_path = config_path.with_suffix(config_path.suffix + ".bak")
        if not backup_path.exists():
            shutil.copy2(config_path, backup_path)
    mode = config_path.stat().st_mode if existed else 0o644
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=config_path.parent,
            prefix=".config.ini-",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write("".join(lines))
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.chmod(temporary_path, mode & 0o777)
        os.replace(temporary_path, config_path)
    except OSError as exc:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise RuntimeError(f"Não consegui configurar a tela cheia: {exc}") from exc
    return config_path


def install_latest_ikemen(
    game_dir: str | Path | None = None,
    progress: ProgressCallback | None = None,
    platform_key: str | None = None,
    character_series: str | None = None,
    setup_sbr: bool = False,
) -> IkemenInstallResult:
    key = _platform_key(platform_key)
    target = Path(game_dir).expanduser().resolve() if game_dir is not None else default_install_dir()
    release = get_latest_stable_release()
    asset = select_platform_asset(release, key)
    checksum = _published_sha256(release, asset)
    if progress:
        progress(f"Preparando IKEMEN GO {release['tag_name']}", 0, 0)

    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".ikemen-download-", dir=target.parent) as temporary_name:
        temporary = Path(temporary_name)
        archive_path = temporary / "ikemen.zip"
        extracted_dir = temporary / "unpacked"
        _download_asset(asset, archive_path, checksum, progress)
        _safe_extract(archive_path, extracted_dir, progress)
        source_root = _find_extracted_game_root(extracted_dir, key)

        if target.exists():
            _merge_missing_files(source_root, target)
            _replace_root_runtime_files(source_root, target, key)
        else:
            # The staging directory is a sibling of the destination so replace is atomic.
            os.replace(source_root, target)

    exe = target / executable_name(key)
    if key == "linux" and exe.is_file() and not os.access(exe, os.X_OK):
        exe.chmod(exe.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    if not _is_usable_executable(exe, key):
        raise RuntimeError("O executável esperado não apareceu após a extração.")
    if not _is_complete_game_installation(target, key):
        raise RuntimeError("O reparo terminou, mas ainda faltam chars/ ou data/select.def.")

    setup_result: SetupResult | None = None
    bundled_results = []
    if setup_sbr:
        bundled_results.extend(_install_bundled_sbr_characters(target))
        script_source = Path(__file__).with_name("setup_ikemen_sbr.py")
        script_target = target / "setup_ikemen_sbr.py"
        if script_source.is_file():
            temporary_script = target / ".setup_ikemen_sbr.py.tmp"
            shutil.copy2(script_source, temporary_script)
            os.replace(temporary_script, script_target)
        setup_result = setup_game(target)
    if character_series is not None:
        bundled_results.extend(install_bundled_character_assets(target, series=character_series))
    return IkemenInstallResult(
        game_dir=target,
        executable=exe,
        version=str(release["tag_name"]),
        downloaded=True,
        setup_result=setup_result,
        bundled_characters=tuple(dict.fromkeys(result.character_entry for result in bundled_results)),
    )


def prepare_jojo_ikemen(
    progress: ProgressCallback | None = None,
    character_series: str | None = None,
    setup_sbr: bool = False,
) -> IkemenInstallResult:
    """Ensure the engine, optionally prepare SBR, and optionally install one local anime package."""
    installed_dir = find_installed_game_dir()
    if installed_dir is not None:
        setup_result: SetupResult | None = None
        bundled_results = []
        if setup_sbr:
            bundled_results.extend(_install_bundled_sbr_characters(installed_dir))
            script_source = Path(__file__).with_name("setup_ikemen_sbr.py")
            script_target = installed_dir / "setup_ikemen_sbr.py"
            if script_source.is_file():
                temporary_script = installed_dir / ".setup_ikemen_sbr.py.tmp"
                shutil.copy2(script_source, temporary_script)
                os.replace(temporary_script, script_target)
            setup_result = setup_game(installed_dir)
        if character_series is not None:
            bundled_results.extend(install_bundled_character_assets(installed_dir, series=character_series))
        if progress:
            progress("IKEMEN GO já instalado" + ("; estrutura SBR conferida" if setup_sbr else ""), 1, 1)
        return IkemenInstallResult(
            game_dir=installed_dir,
            executable=installed_dir / executable_name(),
            version=None,
            downloaded=False,
            setup_result=setup_result,
            bundled_characters=tuple(dict.fromkeys(result.character_entry for result in bundled_results)),
        )
    return install_latest_ikemen(progress=progress, character_series=character_series, setup_sbr=setup_sbr)


def lancar_jojo_ikemen(game_dir: str | Path | None = None) -> tuple[bool, str]:
    """Start an already installed IKEMEN GO process without invoking a shell."""
    if game_dir is None:
        installed_dir = find_installed_game_dir()
        if installed_dir is None:
            return False, "O IKEMEN GO ainda não está instalado. Clique em INSTALAR IKEMEN GO para baixar o pacote oficial."
        root = installed_dir
    else:
        root = Path(game_dir).expanduser().resolve()
    executable = root / executable_name()
    if not _is_usable_executable(executable):
        return False, f"Executável do IKEMEN GO não encontrado em:\n{executable}"
    if not _is_complete_game_installation(root):
        return False, "A instalação do IKEMEN GO está incompleta: faltam chars/ ou data/select.def. Clique em INSTALAR IKEMEN GO para reparar."
    try:
        configurar_tela_cheia(root)
        subprocess.Popen(
            [str(executable)],
            cwd=str(root),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
            close_fds=(os.name != "nt"),
        )
        return True, f"IKEMEN GO iniciado a partir de {root}."
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return False, f"Não consegui iniciar o IKEMEN GO: {exc}"


def abrir_pasta_chars(game_dir: str | Path | None = None) -> tuple[bool, str]:
    """Open the installed chars/ folder in the platform file manager."""
    if game_dir is None:
        installed_dir = find_installed_game_dir()
        if installed_dir is None:
            return False, "Baixe o IKEMEN GO pelo botão JOGAR antes de abrir a pasta chars/."
        root = installed_dir
    else:
        root = Path(game_dir).expanduser().resolve()
    chars = root / "chars"
    if not chars.is_dir():
        return False, f"Pasta de personagens não encontrada:\n{chars}"
    try:
        if sys.platform == "win32":
            os.startfile(str(chars))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(chars)], shell=False)
        else:
            subprocess.Popen(["xdg-open", str(chars)], shell=False)
        return True, str(chars)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return False, f"Não consegui abrir {chars}: {exc}"
