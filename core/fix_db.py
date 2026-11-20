"""Utilitário manual para atualizar uma assinatura válida; sem efeitos ao importar."""

import shutil
from datetime import datetime

from core.security import (
    DB_FILE,
    SecurityStoreError,
    carregar_db_seguro,
    salvar_db_seguro,
)


def main() -> int:
    try:
        database = carregar_db_seguro(DB_FILE)
    except (OSError, SecurityStoreError, ValueError) as exc:
        print(f"Não foi possível validar o banco: {exc}")
        return 1
    if database.get("__hack_detected__") is True:
        print("Assinatura inválida; nenhum arquivo foi alterado. Restaure um backup íntegro.")
        return 2

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = DB_FILE.with_name(f"users.backup-{stamp}.json")
    try:
        shutil.copy2(DB_FILE, backup)
        salvar_db_seguro(database, DB_FILE)
    except (OSError, SecurityStoreError, ValueError) as exc:
        print(f"Falha ao atualizar o banco: {exc}")
        print(f"Se necessário, o arquivo anterior foi copiado para: {backup}")
        return 3
    print(f"Assinatura atualizada após validação. Backup criado: {backup.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
