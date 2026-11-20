from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
DB_FILE = DATA_DIR / "jojo_os.db"
SCHEMA_VERSION = 1
MAX_SCAN_HISTORY = 500


class DatabaseError(RuntimeError):
    """Falha de integridade, versão ou leitura do banco SQLite local."""


def _path(path: str | Path | None = None) -> Path:
    candidate = Path(path) if path is not None else DB_FILE
    return candidate.expanduser().resolve(strict=False)


@contextmanager
def connect_database(path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    db_path = _path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(str(db_path), timeout=15.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 15000")
        connection.execute("PRAGMA journal_mode = DELETE")
        connection.execute("PRAGMA synchronous = FULL")
        ensure_schema(connection)
        yield connection
    except sqlite3.DatabaseError as exc:
        if connection is not None and connection.in_transaction:
            connection.rollback()
        raise DatabaseError("O arquivo SQLite não pôde ser aberto ou atualizado.") from exc
    finally:
        if connection is not None:
            connection.close()


def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS app_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            record_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS scan_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            engine TEXT NOT NULL,
            target TEXT NOT NULL,
            verdict TEXT NOT NULL,
            detections INTEGER NOT NULL DEFAULT 0,
            summary TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT NOT NULL,
            exit_code INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_scan_history_finished
            ON scan_history(finished_at DESC, id DESC);
        """
    )
    row = connection.execute(
        "SELECT value FROM app_metadata WHERE key = 'schema_version'"
    ).fetchone()
    if row is None:
        connection.execute(
            "INSERT INTO app_metadata(key, value) VALUES('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        connection.commit()
        return
    try:
        version = int(row["value"])
    except (TypeError, ValueError) as exc:
        raise DatabaseError("A versão do banco SQLite está inválida.") from exc
    if version > SCHEMA_VERSION:
        raise DatabaseError(
            "O banco foi criado por uma versão mais nova do JoJo-OS. Atualize o aplicativo antes de abri-lo."
        )
    if version < SCHEMA_VERSION:
        connection.execute(
            "UPDATE app_metadata SET value = ? WHERE key = 'schema_version'",
            (str(SCHEMA_VERSION),),
        )
        connection.commit()


def verify_integrity(path: str | Path | None = None) -> None:
    with connect_database(path) as connection:
        result = connection.execute("PRAGMA quick_check").fetchone()
        if result is None or result[0] != "ok":
            raise DatabaseError("A verificação estrutural do banco SQLite falhou.")


def get_metadata(key: str, path: str | Path | None = None) -> str | None:
    with connect_database(path) as connection:
        row = connection.execute(
            "SELECT value FROM app_metadata WHERE key = ?", (key,)
        ).fetchone()
        return str(row["value"]) if row else None


def set_metadata(key: str, value: str, connection: sqlite3.Connection) -> None:
    connection.execute(
        "INSERT INTO app_metadata(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def load_user_records(
    path: str | Path | None = None,
) -> tuple[dict[str, Any], str | None]:
    verify_integrity(path)
    with connect_database(path) as connection:
        rows = connection.execute(
            "SELECT username, record_json FROM users ORDER BY username"
        ).fetchall()
        records: dict[str, Any] = {}
        for row in rows:
            username = row["username"]
            try:
                records[username] = json.loads(row["record_json"])
            except (TypeError, json.JSONDecodeError) as exc:
                raise DatabaseError("Um registro de usuário no banco está malformado.") from exc
        signature_row = connection.execute(
            "SELECT value FROM app_metadata WHERE key = 'users_hmac'"
        ).fetchone()
        signature = str(signature_row["value"]) if signature_row else None
        return records, signature


def save_user_records(
    records: dict[str, Any], signature: str, path: str | Path | None = None
) -> None:
    with connect_database(path) as connection:
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM users")
            connection.executemany(
                "INSERT INTO users(username, record_json) VALUES(?, ?)",
                [
                    (
                        username,
                        json.dumps(
                            value,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                    )
                    for username, value in records.items()
                ],
            )
            set_metadata("users_hmac", signature, connection)
            set_metadata("users_initialized", "1", connection)
            connection.commit()
        except (sqlite3.DatabaseError, TypeError, ValueError) as exc:
            if connection.in_transaction:
                connection.rollback()
            raise DatabaseError("Os usuários não puderam ser salvos no SQLite.") from exc


def get_setting(
    key: str, default: Any = None, path: str | Path | None = None
) -> Any:
    if not isinstance(key, str) or not key or len(key) > 120:
        raise ValueError("A chave da configuração é inválida.")
    with connect_database(path) as connection:
        row = connection.execute(
            "SELECT value_json FROM settings WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row["value_json"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise DatabaseError("Uma configuração do banco está malformada.") from exc


def set_setting(key: str, value: Any, path: str | Path | None = None) -> None:
    if not isinstance(key, str) or not key or len(key) > 120:
        raise ValueError("A chave da configuração é inválida.")
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValueError("A configuração contém dados que não podem ser serializados.") from exc
    updated_at = datetime.now(UTC).isoformat(timespec="seconds")
    with connect_database(path) as connection:
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO settings(key, value_json, updated_at) VALUES(?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json, "
                "updated_at = excluded.updated_at",
                (key, encoded, updated_at),
            )
            connection.commit()
        except sqlite3.DatabaseError as exc:
            if connection.in_transaction:
                connection.rollback()
            raise DatabaseError("A configuração não pôde ser salva no SQLite.") from exc


def delete_setting(key: str, path: str | Path | None = None) -> None:
    if not isinstance(key, str) or not key or len(key) > 120:
        raise ValueError("A chave da configuração é inválida.")
    with connect_database(path) as connection:
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM settings WHERE key = ?", (key,))
            connection.commit()
        except sqlite3.DatabaseError as exc:
            if connection.in_transaction:
                connection.rollback()
            raise DatabaseError("A configuração não pôde ser removida do SQLite.") from exc


def record_scan(
    *,
    engine: str,
    target: str,
    verdict: str,
    detections: int,
    summary: str,
    started_at: str,
    finished_at: str,
    exit_code: int | None,
    path: str | Path | None = None,
) -> int:
    allowed_verdicts = {"clean", "detections", "inconclusive", "error", "cancelled"}
    if verdict not in allowed_verdicts:
        raise ValueError("O resultado da varredura é inválido.")
    values = (
        str(engine)[:120],
        str(target)[:4096],
        verdict,
        max(0, int(detections)),
        str(summary)[:2000],
        str(started_at)[:64],
        str(finished_at)[:64],
        int(exit_code) if exit_code is not None else None,
    )
    with connect_database(path) as connection:
        try:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                "INSERT INTO scan_history(" 
                "engine, target, verdict, detections, summary, started_at, finished_at, exit_code" 
                ") VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                values,
            )
            connection.execute(
                "DELETE FROM scan_history WHERE id NOT IN "
                "(SELECT id FROM scan_history ORDER BY id DESC LIMIT ?)",
                (MAX_SCAN_HISTORY,),
            )
            scan_id = int(cursor.lastrowid)
            connection.commit()
            return scan_id
        except sqlite3.DatabaseError as exc:
            if connection.in_transaction:
                connection.rollback()
            raise DatabaseError("O histórico de varreduras não pôde ser salvo.") from exc


def list_scan_history(
    limit: int = 50, path: str | Path | None = None
) -> list[dict[str, Any]]:
    safe_limit = min(200, max(1, int(limit)))
    with connect_database(path) as connection:
        rows = connection.execute(
            "SELECT id, engine, target, verdict, detections, summary, started_at, finished_at, exit_code "
            "FROM scan_history ORDER BY id DESC LIMIT ?",
            (safe_limit,),
        ).fetchall()
        return [dict(row) for row in rows]


def clear_scan_history(path: str | Path | None = None) -> None:
    with connect_database(path) as connection:
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM scan_history")
            connection.commit()
        except sqlite3.DatabaseError as exc:
            if connection.in_transaction:
                connection.rollback()
            raise DatabaseError("O histórico não pôde ser apagado.") from exc
