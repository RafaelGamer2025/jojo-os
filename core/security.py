from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import tempfile
from pathlib import Path
from typing import Any

from core import database as sqlite_database

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
DB_FILE = DATA_DIR / "jojo_os.db"
LEGACY_DB_FILE = DATA_DIR / "users.json"
SYSTEM_KEY_FILE = DATA_DIR / "system_key.json"
PASSWORD_ITERATIONS = 310_000
PASSWORD_SCHEME = "pbkdf2_sha256"


class SecurityStoreError(RuntimeError):
    """Indica falha ao abrir ou validar o armazenamento local de usuários."""


def _resolve_data_file(path: str | Path | None, default: Path) -> Path:
    candidate = Path(path) if path is not None else default
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    candidate = candidate.resolve(strict=False)
    data_root = DATA_DIR.resolve(strict=False)
    try:
        candidate.relative_to(data_root)
    except ValueError as exc:
        raise ValueError("O arquivo solicitado precisa ficar dentro da pasta data/.") from exc
    return candidate


def _canonical_json(data: Any) -> bytes:
    return json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp:
            temp_name = temp.name
            json.dump(value, temp, ensure_ascii=False, indent=2)
            temp.write("\n")
            temp.flush()
            os.fsync(temp.fileno())
        os.replace(temp_name, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    finally:
        if temp_name and os.path.exists(temp_name):
            try:
                os.unlink(temp_name)
            except OSError:
                pass


def _write_system_key(
    key: str,
    path: str | Path | None = None,
    previous_keys: list[str] | None = None,
) -> None:
    key_path = _resolve_data_file(path, SYSTEM_KEY_FILE)
    payload = {"key": key}
    if previous_keys:
        payload["previous_keys"] = previous_keys
    _atomic_write_json(key_path, payload)


def get_system_key(path: str | Path | None = None) -> str:
    """Carrega a chave local ou cria uma chave aleatória forte no primeiro uso."""
    key_path = _resolve_data_file(path, SYSTEM_KEY_FILE)
    if not key_path.exists():
        key = secrets.token_urlsafe(48)
        _atomic_write_json(key_path, {"key": key})
        return key

    try:
        payload = json.loads(key_path.read_text(encoding="utf-8"))
        key = payload.get("key") if isinstance(payload, dict) else None
    except (OSError, json.JSONDecodeError) as exc:
        raise SecurityStoreError("A chave local do banco não pôde ser lida.") from exc

    if not isinstance(key, str) or not key:
        raise SecurityStoreError("A chave local do banco é inválida.")
    return key


def _get_system_keys(path: str | Path | None = None) -> list[str]:
    key_path = _resolve_data_file(path, SYSTEM_KEY_FILE)
    primary = get_system_key(key_path)
    keys = [primary]
    try:
        payload = json.loads(key_path.read_text(encoding="utf-8"))
        old_keys = payload.get("previous_keys", []) if isinstance(payload, dict) else []
    except (OSError, json.JSONDecodeError) as exc:
        raise SecurityStoreError("A chave local do banco não pôde ser lida.") from exc
    if isinstance(old_keys, list):
        for old in old_keys:
            if isinstance(old, str) and old and old not in keys:
                keys.append(old)
    return keys


def gerar_assinatura(data: Any, key: str) -> str:
    """Gera uma assinatura HMAC-SHA256 para o formato atual."""
    return hmac.new(key.encode("utf-8"), _canonical_json(data), hashlib.sha256).hexdigest()


def _legacy_signature(data: Any, key: str) -> str:
    """Verifica o formato legado SHA256(JSON + chave) apenas para migração."""
    raw = json.dumps(data, sort_keys=True)
    return hashlib.sha256((raw + key).encode("utf-8")).hexdigest()


def _signature_is_valid(data: Any, signature: Any, keys: list[str]) -> bool:
    if not isinstance(signature, str):
        return False
    for key in keys:
        current = gerar_assinatura(data, key)
        legacy = _legacy_signature(data, key)
        if hmac.compare_digest(signature, current) or hmac.compare_digest(signature, legacy):
            return True
    return False


def _unwrap_signed_packages(payload: Any, keys: list[str], depth: int = 0) -> tuple[Any, bool]:
    if depth > 5:
        return None, False
    if not isinstance(payload, dict):
        return None, False

    signature_field = None
    if "assinatura" in payload:
        signature_field = "assinatura"
    elif "signature" in payload:
        signature_field = "signature"

    if "data" not in payload or signature_field is None:
        return payload, True

    inner_data = payload.get("data")
    if not _signature_is_valid(inner_data, payload.get(signature_field), keys):
        return None, False

    unwrapped, valid = _unwrap_signed_packages(inner_data, keys, depth + 1)
    if not valid or not isinstance(unwrapped, dict):
        return None, False

    # Versões antigas chegaram a gravar a conta nova ao lado de um pacote antigo.
    # Após validar a assinatura do invólucro, mesclamos esses registros sem expor metadados.
    metadata = {"data", "assinatura", "signature", "version"}
    siblings = {k: v for k, v in payload.items() if k not in metadata}
    merged = dict(unwrapped)
    merged.update(siblings)
    return merged, True


def _load_legacy_json(db_path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(db_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SecurityStoreError("O banco JSON antigo está ausente ou malformado.") from exc

    if not isinstance(raw, dict):
        raise SecurityStoreError("O banco JSON antigo não contém um objeto válido.")

    keys = _get_system_keys()
    unwrapped, valid = _unwrap_signed_packages(raw, keys)
    if not valid or not isinstance(unwrapped, dict):
        return {"__hack_detected__": True}
    return unwrapped


def _move_legacy_backup(db_path: Path) -> None:
    if not db_path.exists():
        return
    backup = db_path.with_name(f"{db_path.name}.migrated.bak")
    suffix = 1
    while backup.exists():
        backup = db_path.with_name(f"{db_path.name}.migrated-{suffix}.bak")
        suffix += 1
    try:
        os.replace(db_path, backup)
        try:
            os.chmod(backup, 0o600)
        except OSError:
            pass
    except OSError:
        # O SQLite já foi gravado e validado. Se não for possível arquivar o
        # original, ele permanece no lugar e nunca é sobrescrito.
        return


def salvar_db_seguro(db: dict[str, Any], caminho: str | Path = DB_FILE) -> None:
    if not isinstance(db, dict):
        raise TypeError("O banco de usuários precisa ser um objeto.")

    db_path = _resolve_data_file(caminho, DB_FILE)
    if db_path.suffix.lower() != ".db":
        raise ValueError("Contas novas só podem ser gravadas no banco SQLite .db.")
    key_path = _resolve_data_file(SYSTEM_KEY_FILE, SYSTEM_KEY_FILE)
    key = get_system_key(key_path)

    # Mantém a rotação tolerante a interrupções: a chave anterior continua
    # disponível enquanto houver JSON legado que possa ser restaurado.
    rotate_key = len(key.encode("utf-8")) < 32
    previous_keys: list[str] = []
    if rotate_key:
        previous_keys = _get_system_keys(key_path)
        key = secrets.token_urlsafe(48)
        _write_system_key(key, key_path, previous_keys)

    try:
        sqlite_database.save_user_records(db, gerar_assinatura(db, key), db_path)
    except sqlite_database.DatabaseError as exc:
        raise SecurityStoreError("Não foi possível gravar as contas no SQLite.") from exc
    has_legacy_backup = LEGACY_DB_FILE.exists() or any(
        DATA_DIR.glob("users.json.migrated*.bak")
    )
    if not has_legacy_backup:
        _write_system_key(key, key_path)


def carregar_db_seguro(caminho: str | Path = DB_FILE) -> dict[str, Any]:
    db_path = _resolve_data_file(caminho, DB_FILE)

    # Compatibilidade de leitura explícita para ferramentas antigas. O caminho
    # ativo do aplicativo passa a ser sempre jojo_os.db.
    if db_path.suffix.lower() == ".json":
        return _load_legacy_json(db_path)

    if not db_path.exists():
        legacy_path = _resolve_data_file(LEGACY_DB_FILE, LEGACY_DB_FILE)
        legacy_sources = [legacy_path] if legacy_path.exists() else sorted(
            DATA_DIR.glob("users.json.migrated*.bak"),
            key=lambda candidate: candidate.stat().st_mtime,
            reverse=True,
        )
        if legacy_sources:
            source_path = _resolve_data_file(legacy_sources[0], LEGACY_DB_FILE)
            legacy_data = _load_legacy_json(source_path)
            if legacy_data.get("__hack_detected__") is True:
                return legacy_data
            salvar_db_seguro(legacy_data, db_path)
            try:
                with sqlite_database.connect_database(db_path) as connection:
                    sqlite_database.set_metadata(
                        "legacy_users_migrated", "1", connection
                    )
                    connection.commit()
            except sqlite_database.DatabaseError as exc:
                raise SecurityStoreError("As contas foram copiadas, mas o registro da migração falhou.") from exc
            if source_path == legacy_path:
                _move_legacy_backup(legacy_path)
            return legacy_data

        try:
            salvar_db_seguro({}, db_path)
        except sqlite_database.DatabaseError as exc:
            raise SecurityStoreError("Não foi possível inicializar o banco SQLite.") from exc

    try:
        records, signature = sqlite_database.load_user_records(db_path)
    except sqlite_database.DatabaseError as exc:
        raise SecurityStoreError("O banco SQLite está corrompido ou não pôde ser lido.") from exc

    initialized = sqlite_database.get_metadata("users_initialized", db_path)
    if not records and signature is None and initialized is None:
        # A camada de preferências pode ter criado o schema antes do primeiro
        # login. Assina-se explicitamente o estado vazio, uma única vez.
        salvar_db_seguro({}, db_path)
        return {}
    if signature is None:
        return {"__hack_detected__": True}
    if not _signature_is_valid(records, signature, _get_system_keys()):
        return {"__hack_detected__": True}
    if initialized != "1":
        try:
            with sqlite_database.connect_database(db_path) as connection:
                sqlite_database.set_metadata("users_initialized", "1", connection)
                connection.commit()
        except sqlite_database.DatabaseError as exc:
            raise SecurityStoreError("Não foi possível registrar o estado de integridade do banco.") from exc
    return records


def hash_password(password: str) -> str:
    """Hash de senha salgado e lento; o formato inclui versão, salt e iterações."""
    if not isinstance(password, str) or not password:
        raise ValueError("A senha não pode ser vazia.")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_ITERATIONS,
    )
    return f"{PASSWORD_SCHEME}${PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"


def verificar_senha(armazenada: Any, informada: str) -> tuple[bool, bool]:
    """Retorna (válida, precisa_migrar). Aceita SHA-256/plaintext apenas na migração."""
    if not isinstance(informada, str) or not isinstance(armazenada, (str, dict)):
        return False, False
    if isinstance(armazenada, dict):
        armazenada = armazenada.get("value", "")
    if not isinstance(armazenada, str) or not armazenada:
        return False, False

    if armazenada.startswith(f"{PASSWORD_SCHEME}$"):
        try:
            scheme, rounds_text, salt_hex, digest_hex = armazenada.split("$", 3)
            rounds = int(rounds_text)
            salt = bytes.fromhex(salt_hex)
            expected = bytes.fromhex(digest_hex)
            if scheme != PASSWORD_SCHEME or not 100_000 <= rounds <= 1_000_000:
                return False, False
            if not 8 <= len(salt) <= 64 or len(expected) != 32:
                return False, False
            actual = hashlib.pbkdf2_hmac("sha256", informada.encode("utf-8"), salt, rounds)
            return hmac.compare_digest(actual, expected), False
        except (ValueError, TypeError):
            return False, False

    if len(armazenada) == 64 and all(c in "0123456789abcdefABCDEF" for c in armazenada):
        old_hash = hashlib.sha256(informada.encode("utf-8")).hexdigest()
        return hmac.compare_digest(old_hash, armazenada.lower()), True

    # Compatibilidade de uso único com bancos muito antigos que guardavam texto puro.
    return hmac.compare_digest(armazenada, informada), True


def verificar_maquina() -> dict[str, Any]:
    """Retorna metadados locais; não consulta serviços de geolocalização/IP."""
    import platform

    return {"sistema": platform.system(), "versao": platform.release(), "rede_consultada": False}
