"""Downloads e instala personagens MUGEN/IKEMEN de fontes públicas verificadas.

O motor e os personagens são operações separadas. O módulo nunca inicia arquivos
baixados, não usa scraping de páginas protegidas e não contorna login, pagamento,
CAPTCHA, API autenticada ou limites HTTP.
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import html
import json
import os
import re
import shutil
import stat
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath, PureWindowsPath

from core.games.anime_character_import import (
    AnimeImportResult,
    import_character_folder,
    install_bundled_character_assets,
    register_existing_character,
)

ProgressCallback = Callable[[str, int, int], None]
GITHUB_COMMIT = "7951fc472705de6ab32b976798bf8f3f3c9c6736"
GITHUB_REPOSITORY = "amarimono-mugen/products"
GITHUB_TREE_URL = (
    f"https://api.github.com/repos/{GITHUB_REPOSITORY}/git/trees/"
    f"{GITHUB_COMMIT}?recursive=1"
)
MAX_GITHUB_TREE_BYTES = 8 * 1024 * 1024
MAX_CHARACTER_DOWNLOAD_BYTES = 128 * 1024 * 1024
MAX_ITCH_ONE_PIECE_BYTES = 600 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 100_000
MAX_ARCHIVE_UNPACKED_BYTES = 2 * 1024 * 1024 * 1024
MAX_ARCHIVE_MEMBER_BYTES = 512 * 1024 * 1024
CHUNK_SIZE = 256 * 1024
REQUEST_TIMEOUT = 60
USER_AGENT = "JoJo-OS-Character-Installer/1.0"


@dataclass(frozen=True)
class CharacterSource:
    character_id: str
    label: str
    series: str
    kind: str
    enabled: bool = True
    local_series: str = ""
    github_folder: str = ""
    github_definition: str = ""
    itch_user: str = ""
    itch_slug: str = ""
    itch_filename: str = ""
    archive_keyword: str = ""
    max_download_bytes: int = MAX_CHARACTER_DOWNLOAD_BYTES
    creator: str = ""
    source_url: str = ""
    bundled_folder: str = ""
    bundled_target_name: str = ""


@dataclass(frozen=True)
class CharacterBatchFailure:
    character_id: str
    label: str
    error: str


@dataclass(frozen=True)
class CharacterBatchResult:
    total: int
    completed: tuple[str, ...]
    failures: tuple[CharacterBatchFailure, ...]


class _ItchHTTPError(RuntimeError):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


def _github_character(
    character_id: str,
    label: str,
    folder: str,
    definition: str,
) -> CharacterSource:
    return CharacterSource(
        character_id=character_id,
        label=label,
        series="jojo",
        kind="github",
        github_folder=folder,
        github_definition=definition,
        creator="amarimono",
        source_url=f"https://github.com/{GITHUB_REPOSITORY}/tree/{GITHUB_COMMIT}/{urllib.parse.quote(folder)}",
    )


# The repository README states that the creator tested these characters in MUGEN 1.1b
# and IKEMEN GO and imposes no usage restrictions. Every download is pinned to a commit.
_CHARACTER_SOURCES: dict[str, CharacterSource] = {
    "naruto": CharacterSource(
        "naruto", "Naruto — Naruto Uzumaki (já incluído)", "naruto", "bundled",
        local_series="naruto", creator="InSeph / BabyDesu",
        bundled_folder="Naruto_Naruto_Academy", bundled_target_name="Naruto_Naruto_Academy",
    ),
    "jujutsu_yuji": CharacterSource(
        "jujutsu_yuji", "Jujutsu Kaisen — Yuji Itadori (já incluído)", "jujutsu_kaisen", "bundled",
        local_series="jujutsu_kaisen", creator="ScalzerBR / Viniciusonico",
        bundled_folder="JujutsuKaisen_Yuji_Itadori", bundled_target_name="JujutsuKaisen_Yuji_Itadori",
    ),
    "jojo_diego": CharacterSource(
        "jojo_diego", "JoJo — Diego Brando (já incluído)", "jojo", "bundled",
        local_series="jojo", creator="LautyCarp / Gogetacris",
        source_url="Arquivo enviado pela usuária: Diego Brando.zip",
        bundled_folder="JoJo_Diego_Brando", bundled_target_name="Diego_Brando",
    ),
    "jojo_funny_valentine": CharacterSource(
        "jojo_funny_valentine", "JoJo — Funny Valentine (já incluído)", "jojo", "bundled",
        local_series="jojo", creator="caxer602",
        source_url="Arquivo enviado pela usuária: Valentine.zip",
        bundled_folder="JoJo_Funny_Valentine", bundled_target_name="Funny_Valentine",
    ),
    "jojo_jotaro_m_ism": CharacterSource(
        "jojo_jotaro_m_ism", "JoJo — Jotaro Kujo (M-ISM, já incluído)", "jojo", "bundled",
        local_series="jojo", creator="Warusaki3",
        source_url="Arquivo enviado pela usuária: jotaro_m-ism.zip",
        bundled_folder="JoJo_Jotaro_M_Ism", bundled_target_name="JoJo_Jotaro_M_Ism",
    ),
    "jojo_wonder_of_u": CharacterSource(
        "jojo_wonder_of_u", "JoJo — Wonder of U (já incluído)", "jojo", "bundled",
        local_series="jojo", creator="Ice-Bear",
        source_url="Arquivo enviado pela usuária: Wonder Of U.zip",
        bundled_folder="JoJo_Wonder_Of_You", bundled_target_name="JoJo_Wonder_Of_You",
    ),
    "one_piece_zoro": CharacterSource(
        "one_piece_zoro", "One Piece — Roronoa Zoro (já incluído)", "one_piece", "bundled",
        local_series="one_piece", creator="CobraG6",
        source_url="Arquivo enviado pela usuária: G6_Zoro.zip",
        bundled_folder="OnePiece_Roronoa_Zoro", bundled_target_name="OnePiece_Roronoa_Zoro",
    ),
    "jojo_jonathan": _github_character("jojo_jonathan", "JoJo — Jonathan Joestar", "jonathan_asb", "jonathan_asb.def"),
    "jojo_zeppeli": _github_character("jojo_zeppeli", "JoJo — Zeppeli", "zeppeli", "zeppeli.def"),
    "jojo_giorno": _github_character("jojo_giorno", "JoJo — Giorno Giovanna", "Giorno", "Giorno.def"),
    "jojo_requiem_giorno": _github_character("jojo_requiem_giorno", "JoJo — Giorno Requiem", "requiem Giorno", "Requiem Giorno.def"),
    "jojo_jolyne": _github_character("jojo_jolyne", "JoJo — Jolyne Cujoh", "jolyne_asb", "jolyne_asb.def"),
    "jojo_rohan": _github_character("jojo_rohan", "JoJo — Rohan Kishibe", "rohan", "rohan.def"),
    "jojo_kira": _github_character("jojo_kira", "JoJo — Yoshikage Kira", "Kira", "Kira.def"),
    "jojo_kawajiri": _github_character("jojo_kawajiri", "JoJo — Kosaku Kawajiri", "KawajiriKosaku", "KawajiriKosaku.def"),
    "jojo_ghiaccio": _github_character("jojo_ghiaccio", "JoJo — Ghiaccio", "Ghiaccio", "Ghiaccio.def"),
    "jojo_diavolo": _github_character("jojo_diavolo", "JoJo — Diavolo", "diavolo_daibouken", "diavolo_daibouken.def"),
    "jojo_fugo": _github_character("jojo_fugo", "JoJo — Pannacotta Fugo", "fugo", "fugo.def"),
    "jojo_koichi": _github_character("jojo_koichi", "JoJo — Koichi Act 3", "koiti_act3", "koiti_act3.def"),
    "jojo_abbacchio": _github_character("jojo_abbacchio", "JoJo — Leone Abbacchio", "leone abbacchio", "leone abbacchio.def"),
    "jojo_mista": _github_character("jojo_mista", "JoJo — Guido Mista", "mista", "mista.def"),
    "jojo_prosciutto": _github_character("jojo_prosciutto", "JoJo — Prosciutto", "prosciutto _aniki", "prosciutto _aniki.def"),
    "jojo_trish": _github_character("jojo_trish", "JoJo — Trish Una", "trish una", "trish una.def"),
    "jojo_s_diavolo": _github_character("jojo_s_diavolo", "JoJo — S. Diavolo", "s_diavolo", "s_diavolo.def"),
    # Both are public free creator pages. Downloads remain on-demand, use only the
    # standard itch.io flow, and are extracted to the single selected character.
    "dragonball_goku": CharacterSource(
        "dragonball_goku", "Dragon Ball Z — Goku (10 MB)", "dragon_ball", "itch",
        itch_user="nozywolf", itch_slug="goku-mugen-character-stage",
        itch_filename="mugen (goku + kame house).zip", archive_keyword="goku",
        max_download_bytes=100 * 1024 * 1024, creator="Nozywolf",
        source_url="https://nozywolf.itch.io/goku-mugen-character-stage",
    ),
    "one_piece_luffy": CharacterSource(
        "one_piece_luffy", "One Piece — Luffy (jogo completo, 455 MB)", "one_piece", "itch",
        itch_user="todorokibok", itch_slug="one-piece-burning-blood-mugen",
        itch_filename="One Piece Burning Blood MUGEN-v1.1.1.zip", archive_keyword="luffy",
        max_download_bytes=MAX_ITCH_ONE_PIECE_BYTES, creator="todorokibok",
        source_url="https://todorokibok.itch.io/one-piece-burning-blood-mugen",
    ),
}


def character_catalog() -> tuple[CharacterSource, ...]:
    """Return only local or remote entries that have passed source validation."""
    return tuple(source for source in _CHARACTER_SOURCES.values() if source.enabled)


def get_character_source(character_id: str) -> CharacterSource:
    source = _CHARACTER_SOURCES.get(character_id)
    if source is None:
        raise ValueError("Personagem não reconhecido. Escolha uma opção da lista do JoJo-OS.")
    if not source.enabled:
        raise RuntimeError("Este download ainda está em validação e não aparece como disponível no seletor.")
    return source


def _request(url: str, *, accept: str = "*/*", referer: str = "") -> urllib.request.Request:
    headers = {"User-Agent": USER_AGENT, "Accept": accept}
    if referer:
        headers["Referer"] = referer
    if url.startswith("https://api.github.com/"):
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    return urllib.request.Request(url, headers=headers)


def _open_with_retry(request, *, timeout: int, opener=None):
    """Retry transient transport/server failures without bypassing access limits."""
    open_request = opener.open if opener is not None else urllib.request.urlopen
    attempts = 3
    for attempt in range(attempts):
        try:
            return open_request(request, timeout=timeout)
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
    raise RuntimeError("A conexão terminou sem uma resposta válida.")


def _host(url: str) -> str:
    return (urllib.parse.urlparse(url).hostname or "").casefold()


def _read_github_json(url: str) -> dict:
    if _host(url) != "api.github.com":
        raise RuntimeError("O downloader recusou uma API fora do GitHub oficial.")
    try:
        with _open_with_retry(
            _request(url, accept="application/vnd.github+json"),
            timeout=REQUEST_TIMEOUT,
        ) as response:
            if _host(response.geturl()) != "api.github.com":
                raise RuntimeError("O GitHub redirecionou a API para um host inesperado.")
            data = response.read(MAX_GITHUB_TREE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"GitHub respondeu HTTP {exc.code} ao listar o personagem.") from exc
    if len(data) > MAX_GITHUB_TREE_BYTES:
        raise RuntimeError("A árvore do GitHub excede o limite de segurança.")
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("A resposta do GitHub não é um JSON válido.") from exc
    if not isinstance(payload, dict):
        raise TypeError("A árvore do GitHub retornou um formato inesperado.")
    return payload


def _git_blob_sha(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def _safe_repo_relative(value: str) -> PurePosixPath:
    normalized = value.replace("\\", "/")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(normalized)
    if (
        not posix.parts
        or posix.is_absolute()
        or windows.is_absolute()
        or windows.drive
        or any(part in {"", ".", ".."} for part in posix.parts)
        or any("\x00" in part for part in posix.parts)
    ):
        raise RuntimeError(f"O pacote contém um caminho inseguro: {value!r}.")
    return posix


def _download_github_character(
    source: CharacterSource,
    destination: Path,
    progress: ProgressCallback | None = None,
    *,
    tree_payload: dict | None = None,
) -> Path:
    payload = tree_payload if tree_payload is not None else _read_github_json(GITHUB_TREE_URL)
    if payload.get("truncated"):
        raise RuntimeError("A listagem do GitHub foi truncada; o download foi cancelado.")
    tree = payload.get("tree")
    if not isinstance(tree, list):
        raise TypeError("A árvore do GitHub não contém uma lista de arquivos.")

    prefix = source.github_folder.rstrip("/") + "/"
    files: list[dict] = []
    for item in tree:
        if not isinstance(item, dict) or item.get("type") != "blob":
            continue
        path = item.get("path")
        if not isinstance(path, str) or not path.startswith(prefix):
            continue
        relative = path[len(prefix):]
        safe_relative = _safe_repo_relative(relative)
        mode = item.get("mode")
        if mode == "120000":
            raise RuntimeError("O personagem contém um link simbólico não permitido.")
        size = item.get("size")
        sha = item.get("sha")
        if not isinstance(size, int) or size < 0 or size > MAX_ARCHIVE_MEMBER_BYTES:
            raise RuntimeError(f"Tamanho inválido no arquivo GitHub {relative!r}.")
        if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise RuntimeError(f"Hash Git inválido para {relative!r}.")
        files.append({"path": path, "relative": safe_relative, "size": size, "sha": sha})

    if not files:
        raise RuntimeError(f"A pasta {source.github_folder} não tem arquivos públicos no commit pinado.")
    total = sum(item["size"] for item in files)
    if total > MAX_CHARACTER_DOWNLOAD_BYTES:
        raise RuntimeError("O personagem excede o limite de 128 MiB; nada foi instalado.")
    expected_def = _safe_repo_relative(source.github_definition)
    if not any(item["relative"] == expected_def for item in files):
        raise RuntimeError(f"O .def esperado não existe na pasta pública: {source.github_definition}.")
    if not any(item["relative"].suffix.casefold() == ".sff" for item in files):
        raise RuntimeError("A pasta pública não contém arquivo de sprites .sff.")

    source_root = destination / source.github_folder
    source_root.mkdir(parents=True, exist_ok=True)

    def fetch_blob(item: dict) -> bytes:
        encoded = urllib.parse.quote(item["path"], safe="/")
        url = f"https://raw.githubusercontent.com/{GITHUB_REPOSITORY}/{GITHUB_COMMIT}/{encoded}"
        try:
            with _open_with_retry(_request(url), timeout=REQUEST_TIMEOUT) as response:
                if _host(response.geturl()) != "raw.githubusercontent.com":
                    raise RuntimeError("Um download do GitHub foi redirecionado a um host inesperado.")
                data = response.read(item["size"] + 1)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"GitHub respondeu HTTP {exc.code} ao baixar {item['relative']}.") from exc
        if len(data) != item["size"]:
            raise RuntimeError(f"Download incompleto ou maior que o esperado: {item['relative']}.")
        if _git_blob_sha(data) != item["sha"]:
            raise RuntimeError(f"O hash Git do arquivo não confere: {item['relative']}.")
        return data

    completed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        future_map = {pool.submit(fetch_blob, item): item for item in files}
        for future in concurrent.futures.as_completed(future_map):
            item = future_map[future]
            data = future.result()
            relative_path = Path(*item["relative"].parts)
            target = source_root / relative_path
            resolved = target.resolve()
            root_resolved = source_root.resolve()
            if resolved != root_resolved and root_resolved not in resolved.parents:
                raise RuntimeError("O download tentou sair da pasta temporária do personagem.")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            completed += item["size"]
            if progress:
                progress(f"Baixando arquivos de {source.label}", completed, total)

    definition = source_root / Path(*expected_def.parts)
    if not definition.is_file():
        raise RuntimeError("O arquivo .def principal não apareceu depois do download.")
    _write_source_credit(source_root, source, f"GitHub commit {GITHUB_COMMIT}")
    return source_root


class _ItchPageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.csrf = ""
        self.download_buttons: list[str] = []
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: (value or "") for key, value in attrs}
        if tag == "meta" and values.get("name", "").casefold() == "csrf_token":
            self.csrf = values.get("value") or values.get("content", "")
        if tag == "input" and values.get("name", "").casefold() == "csrf_token":
            self.csrf = values.get("value", self.csrf)
        classes = set(values.get("class", "").split())
        if tag in {"a", "button"} and "download_btn" in classes:
            upload_id = values.get("data-upload_id", "")
            if upload_id.isdigit():
                self.download_buttons.append(upload_id)

    def handle_data(self, data: str) -> None:
        self.text.append(data)


def _itch_open(opener, url: str, *, data: bytes | None = None, referer: str = "") -> tuple[bytes, str, dict[str, str]]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/json,application/octet-stream,*/*",
    }
    if referer:
        headers["Referer"] = referer
    if data is not None:
        headers.update({
            "Origin": f"https://{urllib.parse.urlparse(url).hostname}",
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Requested-With": "XMLHttpRequest",
        })
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with _open_with_retry(request, timeout=REQUEST_TIMEOUT, opener=opener) as response:
            return response.read(2 * 1024 * 1024), response.geturl(), dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise _ItchHTTPError(404, "itch.io respondeu HTTP 404 para a rota solicitada.") from exc
        if exc.code == 429:
            retry_after = exc.headers.get("Retry-After", "")
            suffix = f" Tente de novo depois de {retry_after} segundos." if retry_after.isdigit() else " Tente novamente mais tarde."
            raise RuntimeError("itch.io limitou temporariamente os pedidos." + suffix) from exc
        if exc.code in {401, 403, 402}:
            raise RuntimeError("A fonte recusou o acesso gratuito; o JoJo-OS não contornará essa barreira.") from exc
        raise RuntimeError(f"itch.io respondeu HTTP {exc.code}; nada foi instalado.") from exc


def _itch_post_json(opener, url: str, csrf: str, referer: str, allowed_host: str) -> dict:
    form = urllib.parse.urlencode({"csrf_token": csrf}).encode("ascii")
    data, final_url, _headers = _itch_open(opener, url, data=form, referer=referer)
    if _host(final_url) != allowed_host:
        raise RuntimeError("O itch.io redirecionou uma operação para um host inesperado.")
    try:
        result = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("O itch.io não retornou a resposta JSON do botão de download.") from exc
    if not isinstance(result, dict):
        raise TypeError("O itch.io retornou um formato de download inesperado.")
    if result.get("errors"):
        raise RuntimeError("O itch.io recusou o download gratuito: " + "; ".join(map(str, result["errors"])))
    return result


def _itch_allowed_file_host(host: str) -> bool:
    host = host.casefold()
    return host in {"itch.io", "itch.zone"} or host.endswith((".itch.io", ".itch.zone"))


def _download_itch_archive(
    source: CharacterSource,
    destination: Path,
    progress: ProgressCallback | None = None,
) -> Path:
    host = f"{source.itch_user}.itch.io"
    base = f"https://{host}/{source.itch_slug}"
    purchase_url = base + "/purchase"
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
    if progress:
        progress(f"Verificando a página gratuita de {source.label}", 0, 0)

    direct_download_page = False
    try:
        purchase_html, purchase_final, _headers = _itch_open(opener, purchase_url, referer=base)
    except _ItchHTTPError as exc:
        if exc.status_code != 404:
            raise
        # Free itch.io projects can expose a download page without a /purchase route.
        fallback_page: tuple[bytes, str, dict[str, str]] | None = None
        for candidate_url in (base + "/download", base):
            try:
                fallback_page = _itch_open(opener, candidate_url, referer=base)
                break
            except _ItchHTTPError as fallback_exc:
                if fallback_exc.status_code != 404:
                    raise
        if fallback_page is None:
            raise RuntimeError("Não encontrei uma página pública de download para este produto gratuito.") from exc
        purchase_html, purchase_final, _headers = fallback_page
        direct_download_page = True
    if _host(purchase_final) != host:
        raise RuntimeError("A página de origem redirecionou para outro host.")
    purchase_parser = _ItchPageParser()
    purchase_parser.feed(purchase_html.decode("utf-8", "replace"))
    purchase_text = html.unescape(" ".join(purchase_parser.text) + " " + purchase_html.decode("utf-8", "replace")).casefold()
    if source.itch_filename.casefold() not in purchase_text:
        raise RuntimeError("O arquivo listado na página do autor mudou; download cancelado.")
    direct_download_page = direct_download_page or (
        bool(purchase_parser.csrf)
        and len(purchase_parser.download_buttons) == 1
        and source.itch_filename.casefold() in purchase_text
    )
    if direct_download_page:
        intermediate = purchase_final
        download_html = purchase_html
        download_parser = purchase_parser
        download_text = purchase_html.decode("utf-8", "replace")
    else:
        if not purchase_parser.csrf or "no thanks" not in purchase_text:
            raise RuntimeError("A página não oferece um fluxo gratuito público; o app não pagará nem pedirá login.")
        free_result = _itch_post_json(opener, base + "/download_url", purchase_parser.csrf, purchase_url, host)
        intermediate = free_result.get("url")
        if not isinstance(intermediate, str):
            raise TypeError("A opção gratuita não retornou a página pública de downloads.")
        intermediate = urllib.parse.urljoin(base + "/", intermediate)
        parsed_intermediate = urllib.parse.urlparse(intermediate)
        if parsed_intermediate.scheme != "https" or parsed_intermediate.hostname != host:
            raise RuntimeError("O link temporário gratuito aponta para um host inesperado.")
        if f"/{source.itch_slug}/download/" not in parsed_intermediate.path:
            raise RuntimeError("O link temporário não corresponde à página de arquivos esperada.")
        download_html, download_final, _headers = _itch_open(opener, intermediate, referer=purchase_url)
        if _host(download_final) != host:
            raise RuntimeError("A página de arquivos redirecionou para um host inesperado.")
        download_text = download_html.decode("utf-8", "replace")
        download_parser = _ItchPageParser()
        download_parser.feed(download_text)
    combined_text = html.unescape(" ".join(download_parser.text) + " " + download_text).casefold()
    if not download_parser.csrf or source.itch_filename.casefold() not in combined_text:
        raise RuntimeError("A página temporária não contém o arquivo esperado ou token CSRF.")
    if len(download_parser.download_buttons) != 1:
        raise RuntimeError("A página não tem um único botão público de arquivo; download cancelado.")

    file_url = f"https://{host}/{source.itch_slug}/file/{download_parser.download_buttons[0]}?source=game_download"
    file_result = _itch_post_json(opener, file_url, download_parser.csrf, intermediate, host)
    direct_url = file_result.get("url")
    if not isinstance(direct_url, str):
        raise TypeError("O botão gratuito não retornou um link de arquivo.")
    direct_url = urllib.parse.urljoin(base + "/", direct_url)
    if urllib.parse.urlparse(direct_url).scheme != "https" or not _itch_allowed_file_host(_host(direct_url)):
        raise RuntimeError("O link final do itch.io aponta para um host não permitido.")

    archive_path = destination / "source.zip"
    request = _request(direct_url, accept="application/octet-stream", referer=intermediate)
    digest = hashlib.sha256()
    downloaded = 0
    try:
        with _open_with_retry(request, timeout=REQUEST_TIMEOUT) as response:
            if not _itch_allowed_file_host(_host(response.geturl())):
                raise RuntimeError("O download foi redirecionado para um host não permitido.")
            header = response.headers.get("Content-Length", "")
            total = int(header) if header.isdigit() else 0
            if total > source.max_download_bytes:
                raise RuntimeError("O pacote ultrapassa o limite anunciado para este personagem.")
            with archive_path.open("wb") as output:
                if progress:
                    progress(f"Baixando {source.itch_filename}", 0, total)
                while True:
                    chunk = response.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    downloaded += len(chunk)
                    if downloaded > source.max_download_bytes:
                        raise RuntimeError("O download ultrapassou o limite de tamanho; arquivo descartado.")
                    output.write(chunk)
                    digest.update(chunk)
                    if progress:
                        progress(f"Baixando {source.itch_filename}", downloaded, total)
                output.flush()
                os.fsync(output.fileno())
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise RuntimeError("itch.io limitou temporariamente o arquivo. Tente novamente mais tarde.") from exc
        raise RuntimeError(f"O servidor do itch.io respondeu HTTP {exc.code} no arquivo.") from exc
    if downloaded == 0:
        raise RuntimeError("O servidor não entregou o arquivo.")
    with archive_path.open("rb") as archive:
        if archive.read(4) not in {b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"}:
            raise RuntimeError("O arquivo recebido não é um ZIP válido.")
    if progress:
        progress("Download recebido; conferindo o ZIP e a pasta do personagem", downloaded, downloaded)
    # Keep the hash beside the temporary file for diagnostics, never as a trust claim.
    (destination / "source.sha256").write_text(digest.hexdigest() + "\n", encoding="ascii")
    return archive_path


def _zip_safe_name(name: str) -> PurePosixPath:
    normalized = name.replace("\\", "/")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(normalized)
    if (
        posix.is_absolute()
        or windows.is_absolute()
        or windows.drive
        or not posix.parts
        or any(part in {"", ".", ".."} for part in posix.parts)
        or any("\x00" in part for part in posix.parts)
    ):
        raise RuntimeError(f"O ZIP contém um caminho inseguro: {name!r}.")
    return posix


def _select_archive_character(infos: list[zipfile.ZipInfo], keyword: str) -> tuple[PurePosixPath, zipfile.ZipInfo]:
    key = keyword.casefold()
    files = [item for item in infos if not item.is_dir()]
    candidates: dict[tuple[str, ...], list[zipfile.ZipInfo]] = {}
    for item in files:
        path = _zip_safe_name(item.filename)
        if path.suffix.casefold() != ".def":
            continue
        parent_parts = path.parts[:-1]
        matching_indices = [index for index, part in enumerate(parent_parts) if key in part.casefold()]
        if not matching_indices:
            continue
        folder_parts = parent_parts[: matching_indices[-1] + 1]
        if not folder_parts:
            continue
        prefix = PurePosixPath(*folder_parts)
        candidates.setdefault(tuple(folder_parts), []).append(item)

    playable: list[tuple[PurePosixPath, zipfile.ZipInfo]] = []
    for parts, definitions in candidates.items():
        prefix = PurePosixPath(*parts)
        prefix_text = prefix.as_posix().casefold() + "/"
        has_sff = any(
            _zip_safe_name(item.filename).as_posix().casefold().startswith(prefix_text)
            and _zip_safe_name(item.filename).suffix.casefold() == ".sff"
            for item in files
        )
        if not has_sff:
            continue
        definitions.sort(
            key=lambda item: (
                item.filename.rsplit("/", 1)[-1].rsplit(".", 1)[0].casefold() != key,
                item.filename.casefold(),
            )
        )
        playable.append((prefix, definitions[0]))
    if playable:
        deepest = max(len(prefix.parts) for prefix, _definition in playable)
        playable = [item for item in playable if len(item[0].parts) == deepest]
    if len(playable) != 1:
        raise RuntimeError(
            f"Não consegui identificar uma única pasta MUGEN completa de {keyword}; "
            "o pacote não foi instalado."
        )
    return playable[0]


def _extract_archive_character(
    archive_path: Path,
    source: CharacterSource,
    destination: Path,
    progress: ProgressCallback | None = None,
) -> Path:
    try:
        archive = zipfile.ZipFile(archive_path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise RuntimeError("O pacote baixado não é um arquivo ZIP íntegro.") from exc
    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_ARCHIVE_ENTRIES:
            raise RuntimeError("O ZIP tem arquivos demais; foi recusado.")
        if sum(item.file_size for item in infos) > MAX_ARCHIVE_UNPACKED_BYTES:
            raise RuntimeError("O ZIP descompactado ultrapassa o limite de 2 GiB.")
        bad_file = archive.testzip()
        if bad_file:
            raise RuntimeError(f"CRC inválido no ZIP: {bad_file}.")
        prefix, definition_info = _select_archive_character(infos, source.archive_keyword)
        # The archive may be a complete fan game. Extract only the selected character folder.
        output_name = re.sub(r"[^A-Za-z0-9_-]+", "_", definition_info.filename.rsplit("/", 1)[-1].rsplit(".", 1)[0]).strip("_-")
        if not output_name:
            raise RuntimeError("O arquivo .def selecionado tem um nome de pasta inválido.")
        root = destination / output_name
        root.mkdir(parents=True, exist_ok=False)
        selected = [
            item for item in infos
            if not item.is_dir()
            and _zip_safe_name(item.filename).as_posix().casefold().startswith(prefix.as_posix().casefold() + "/")
        ]
        selected_bytes = sum(item.file_size for item in selected)
        if selected_bytes > MAX_ARCHIVE_MEMBER_BYTES:
            raise RuntimeError("A pasta selecionada do personagem ultrapassa o limite seguro de 512 MiB.")
        extracted = 0
        forbidden_suffixes = {".exe", ".dll", ".msi", ".com", ".scr", ".bat", ".ps1", ".sh"}
        for item in selected:
            name = _zip_safe_name(item.filename)
            mode = (item.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(mode):
                raise RuntimeError("A pasta do personagem contém um link simbólico não permitido.")
            relative_parts = name.parts[len(prefix.parts):]
            if not relative_parts:
                continue
            relative = PurePosixPath(*relative_parts)
            if relative.suffix.casefold() in forbidden_suffixes:
                raise RuntimeError(f"A pasta do personagem contém um executável não permitido: {relative.name}.")
            target = root.joinpath(*relative.parts)
            resolved = target.resolve()
            root_resolved = root.resolve()
            if resolved != root_resolved and root_resolved not in resolved.parents:
                raise RuntimeError("A extração tentou sair da pasta temporária do personagem.")
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(item, "r") as incoming, target.open("wb") as outgoing:
                shutil.copyfileobj(incoming, outgoing, length=CHUNK_SIZE)
            extracted += item.file_size
            if progress:
                progress(f"Extraindo somente {source.archive_keyword.title()}", extracted, selected_bytes)

        expected_def = root / definition_info.filename.rsplit("/", 1)[-1]
        if not expected_def.is_file():
            raise RuntimeError("O .def selecionado não foi extraído.")
        if not any(path.is_file() and path.suffix.casefold() == ".sff" for path in root.rglob("*")):
            raise RuntimeError("A pasta selecionada não contém sprites .sff.")
        _write_source_credit(root, source, "arquivo ZIP público do criador, CRC validado")
        return root


def _write_source_credit(root: Path, source: CharacterSource, detail: str) -> None:
    source_file = root / "JOJO_OS_ORIGEM.txt"
    text = (
        f"Personagem: {source.label}\n"
        f"ID do pacote JoJo-OS: {source.character_id}\n"
        f"Criador/fonte declarada: {source.creator}\n"
        f"Origem: {source.source_url}\n"
        f"Detalhe: {detail}\n"
        "O JoJo-OS baixa e instala apenas após a escolha explícita no seletor. "
        "A existência do download não concede direitos sobre as franquias ou materiais de terceiros.\n"
    )
    source_file.write_text(text, encoding="utf-8")


def _register_existing_download(root: Path, source: CharacterSource) -> AnimeImportResult | None:
    chars_dir = root / "chars"
    if chars_dir.is_symlink() or not chars_dir.is_dir():
        return None
    matches: list[Path] = []
    for child in chars_dir.iterdir():
        if child.is_symlink() or not child.is_dir():
            continue
        credit = child / "JOJO_OS_ORIGEM.txt"
        if credit.is_symlink() or not credit.is_file():
            continue
        try:
            lines = credit.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        if f"ID do pacote JoJo-OS: {source.character_id}" in lines:
            matches.append(child)
    if len(matches) > 1:
        raise RuntimeError("Há mais de uma pasta marcada para este pacote; nada foi alterado.")
    if matches:
        return register_existing_character(root, source.series, matches[0])
    return None


def _definition_references(definition: Path) -> tuple[str, ...]:
    try:
        text = definition.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        text = definition.read_text(encoding="cp1252")
    in_files = False
    references: list[str] = []
    allowed_keys = {"sprite", "anim", "cmd", "cns", "st", "stcommon", "sound", "zss"}
    for raw_line in text.splitlines():
        line = raw_line.split(";", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            in_files = line[1:-1].strip().casefold() == "files"
            continue
        if not in_files or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip().casefold() not in allowed_keys:
            continue
        for item in value.split(","):
            reference = item.strip().strip("\"'").replace("\\", "/")
            if not reference or reference.casefold() in {"none", "not used", "-1"}:
                continue
            _safe_repo_relative(reference)
            if not PurePosixPath(reference).suffix:
                continue
            references.append(reference)
    return tuple(dict.fromkeys(references))


def _resolve_case_insensitive(root: Path, relative: PurePosixPath) -> Path | None:
    current = root
    for part in relative.parts:
        if not current.is_dir():
            return None
        exact = current / part
        if exact.exists():
            current = exact
            continue
        match = next((child for child in current.iterdir() if child.name.casefold() == part.casefold()), None)
        if match is None:
            return None
        current = match
    return current if current.is_file() else None


def _validate_definition_references(source_root: Path, game_dir: Path, definition: Path) -> None:
    references = _definition_references(definition)
    if not any(PurePosixPath(item).suffix.casefold() == ".sff" for item in references):
        raise RuntimeError("O .def não referencia um arquivo de sprites .sff.")
    missing: list[str] = []
    for reference in references:
        relative = _safe_repo_relative(reference)
        if _resolve_case_insensitive(source_root, relative) is None and _resolve_case_insensitive(game_dir, relative) is None:
            missing.append(reference)
    if missing:
        names = ", ".join(missing[:6])
        extra = "…" if len(missing) > 6 else ""
        raise RuntimeError(f"O pacote está incompleto; faltam arquivos citados no .def: {names}{extra}.")


def install_all_characters(
    game_dir: str | Path,
    progress: ProgressCallback | None = None,
) -> CharacterBatchResult:
    """Install the whole catalog serially, keeping successful items on partial failure."""
    priority = {"bundled": 0, "github": 1, "itch": 2}
    sources = tuple(sorted(character_catalog(), key=lambda item: (priority.get(item.kind, 99), item.character_id)))
    root = Path(game_dir).expanduser().resolve()
    total = len(sources)
    completed: list[str] = []
    failures: list[CharacterBatchFailure] = []
    tree_payload: dict | None = None
    tree_loaded = False
    tree_error = ""
    progress_scale = 1000

    def report_item(index: int, message: str, current: int, item_total: int) -> None:
        if progress is None:
            return
        fraction = min(1.0, max(0.0, current / item_total)) if item_total > 0 else 0.0
        scaled = index * progress_scale + int(fraction * progress_scale)
        progress(f"[{index + 1}/{total}] {message}", scaled, total * progress_scale)

    def report_done(index: int, source: CharacterSource, message: str) -> None:
        if progress is not None:
            progress(
                f"[{index + 1}/{total}] {source.label}: {message}",
                (index + 1) * progress_scale,
                total * progress_scale,
            )

    for index, source in enumerate(sources):
        if source.kind in {"github", "itch"}:
            try:
                existing = _register_existing_download(root, source)
            except Exception as exc:  # noqa: BLE001 - continue the remaining characters.
                failures.append(CharacterBatchFailure(source.character_id, source.label, f"{type(exc).__name__}: {exc}"))
                report_done(index, source, "falhou ao validar instalação existente")
                continue
            if existing is not None:
                completed.append(source.character_id)
                report_done(index, source, "já estava instalado; select.def conferido")
                continue

        if source.kind == "github" and not tree_loaded:
            tree_loaded = True
            try:
                tree_payload = _read_github_json(GITHUB_TREE_URL)
                if tree_payload.get("truncated") or not isinstance(tree_payload.get("tree"), list):
                    raise RuntimeError("A árvore do GitHub está incompleta ou inválida.")
            except Exception as exc:  # noqa: BLE001 - share one API failure, do not hammer the endpoint.
                tree_error = f"Não foi possível consultar a árvore GitHub uma vez para o lote: {type(exc).__name__}: {exc}"
        if source.kind == "github" and tree_error:
            failures.append(CharacterBatchFailure(source.character_id, source.label, tree_error))
            report_done(index, source, "fonte temporariamente indisponível")
            continue

        try:
            install_selected_character(
                root,
                source.character_id,
                progress=lambda message, current, item_total, item_index=index: report_item(
                    item_index, message, current, item_total
                ),
                _github_tree_payload=tree_payload if source.kind == "github" else None,
            )
        except Exception as exc:  # noqa: BLE001 - report one failure and keep processing the batch.
            failures.append(CharacterBatchFailure(source.character_id, source.label, f"{type(exc).__name__}: {exc}"))
            report_done(index, source, "falhou; os demais continuam")
        else:
            completed.append(source.character_id)
            report_done(index, source, "instalado e registrado")

    return CharacterBatchResult(total=total, completed=tuple(completed), failures=tuple(failures))


def install_selected_character(
    game_dir: str | Path,
    character_id: str,
    progress: ProgressCallback | None = None,
    *,
    _github_tree_payload: dict | None = None,
) -> AnimeImportResult:
    """Download or copy only the selected character, validate it, and update select.def."""
    source = get_character_source(character_id)
    root = Path(game_dir).expanduser().resolve()
    if source.kind == "bundled":
        folders = (source.bundled_folder,) if source.bundled_folder else None
        names = (
            {source.bundled_folder: source.bundled_target_name or source.bundled_folder}
            if source.bundled_folder
            else None
        )
        results = install_bundled_character_assets(
            root,
            series=source.local_series,
            folder_names=folders,
            destination_names=names,
        )
        if len(results) != 1:
            raise RuntimeError(f"O pacote local de {source.label} não foi encontrado ou é inválido.")
        return results[0]

    existing = _register_existing_download(root, source)
    if existing is not None:
        return existing

    with tempfile.TemporaryDirectory(prefix="jojoos-character-") as temporary_name:
        temporary = Path(temporary_name)
        if source.kind == "github":
            source_root = _download_github_character(
                source,
                temporary,
                progress,
                tree_payload=_github_tree_payload,
            )
        elif source.kind == "itch":
            archive_path = _download_itch_archive(source, temporary, progress)
            source_root = _extract_archive_character(archive_path, source, temporary, progress)
        else:
            raise RuntimeError("Tipo de fonte de personagem não suportado.")
        definitions = [path for path in source_root.iterdir() if path.is_file() and path.suffix.casefold() == ".def"]
        matching = [path for path in definitions if path.stem.casefold() == source_root.name.casefold()]
        if len(matching) == 1:
            definition = matching[0]
        elif len(definitions) == 1:
            definition = definitions[0]
        else:
            names = ", ".join(path.name for path in definitions)
            raise RuntimeError(f"A pasta tem vários .def e nenhum principal inequívoco: {names}.")
        if not any(path.is_file() and path.suffix.casefold() == ".sff" for path in source_root.rglob("*")):
            raise RuntimeError("O personagem não tem um arquivo .sff real de sprites.")
        _validate_definition_references(source_root, root, definition)
        result = import_character_folder(
            root,
            source.series,
            source_root,
            permission_confirmed=True,
        )
        return result
