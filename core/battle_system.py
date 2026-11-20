from __future__ import annotations

import random
from typing import Any

from core.stand_awakening import ALL_STANDS

STANDS: dict[str, dict[str, Any]] = {
    "Star Platinum": {
        "power": 9, "speed": 10, "range": 3,
        "skill": "ORA ORA BARRAGE", "desc": "Uma sequência de golpes rápidos.",
        "crit": 0.30, "color": "#4361EE",
    },
    "The World": {
        "power": 10, "speed": 9, "range": 4,
        "skill": "ZA WARUDO", "desc": "Pode parar o tempo por um turno.",
        "time_stop": True, "color": "#FFD60A",
    },
    "Killer Queen": {
        "power": 8, "speed": 7, "range": 5,
        "skill": "BITE THE DUST", "desc": "Pode adicionar dano explosivo.",
        "bomb": True, "color": "#FF4D6D",
    },
    "D4C": {
        "power": 8, "speed": 7, "range": 8,
        "skill": "LOVE TRAIN", "desc": "Pode bloquear parte do ataque recebido.",
        "love_train": True, "color": "#80ED99",
    },
    "Wonder of U": {
        "power": 7, "speed": 8, "range": 10,
        "skill": "CALAMITY", "desc": "Pode devolver parte do dano recebido.",
        "reflect": True, "color": "#9D4EDD",
    },
}

for stand_card in ALL_STANDS:
    STANDS.setdefault(
        stand_card.name,
        {
            "power": 6,
            "speed": 6,
            "range": 6,
            "skill": f"{(stand_card.arcana or stand_card.group).upper()} AWAKENING",
            "desc": stand_card.description,
            "crit": 0.10,
            "color": stand_card.color,
        },
    )

MAX_HP = 100


def criar_lutador(stand: str) -> dict[str, Any]:
    if stand not in STANDS:
        raise ValueError(f"Stand desconhecido: {stand!r}")
    return {"stand": stand, "hp": MAX_HP, "max_hp": MAX_HP}


def _validate_fighter(fighter: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(fighter, dict) or fighter.get("stand") not in STANDS:
        raise ValueError("Lutador ou Stand inválido.")
    try:
        fighter["hp"] = max(0, min(int(fighter.get("hp", MAX_HP)), int(fighter.get("max_hp", MAX_HP))))
    except (TypeError, ValueError):
        fighter["hp"] = MAX_HP
    fighter["max_hp"] = max(1, int(fighter.get("max_hp", MAX_HP)))
    return fighter


def _roll_attack(fighter: dict[str, Any], rng) -> tuple[int, list[str]]:
    stand = STANDS[fighter["stand"]]
    damage = rng.randint(10, 20) + int(stand["power"])
    messages: list[str] = []
    if rng.random() < float(stand.get("crit", 0.0)):
        damage *= 2
        messages.append(f"CRÍTICO de {fighter['stand']}!")
    if stand.get("bomb") and rng.random() < 0.30:
        damage += 15
        messages.append("BITE THE DUST! +15 de dano.")
    return damage, messages


def turno_batalha(player: dict[str, Any], enemy: dict[str, Any], rng=None) -> list[str]:
    """Executa uma rodada; modifica HP in-place e nunca deixa HP negativo.

    `rng` é injetável para testes determinísticos. Time Stop pode cancelar
    a resposta do alvo, Love Train reduz dano recebido e Reflect devolve 30%.
    """
    rng = rng or random
    player = _validate_fighter(player)
    enemy = _validate_fighter(enemy)
    log: list[str] = []

    if player["hp"] <= 0 or enemy["hp"] <= 0:
        log.append("A batalha já terminou.")
        return log

    player_stand = STANDS[player["stand"]]
    enemy_stand = STANDS[enemy["stand"]]

    damage_to_enemy, player_msgs = _roll_attack(player, rng)
    damage_to_player, enemy_msgs = _roll_attack(enemy, rng)
    log.extend(player_msgs)
    log.extend(enemy_msgs)

    # O atacante que possui ZA WARUDO tenta congelar a resposta adversária.
    player_stopped_time = bool(player_stand.get("time_stop") and rng.random() < 0.30)
    enemy_stopped_time = bool(enemy_stand.get("time_stop") and rng.random() < 0.30)
    if player_stopped_time:
        log.append("ZA WARUDO! A resposta do oponente foi interrompida.")
    if enemy_stopped_time:
        log.append("ZA WARUDO! Seu ataque foi interrompido.")

    if not enemy_stopped_time:
        if enemy_stand.get("love_train") and rng.random() < 0.40:
            log.append("LOVE TRAIN desviou o ataque recebido!")
            damage_to_enemy = 0
        applied = min(enemy["hp"], max(0, damage_to_enemy))
        enemy["hp"] -= applied
        log.append(f"Você causou {applied} de dano.")
        if enemy_stand.get("reflect") and applied:
            reflected = min(player["hp"], int(applied * 0.30))
            player["hp"] -= reflected
            if reflected:
                log.append(f"CALAMITY refletiu {reflected} de dano para você.")
    else:
        log.append("Seu ataque não chegou ao alvo.")

    if enemy["hp"] > 0 and not player_stopped_time:
        if player_stand.get("love_train") and rng.random() < 0.40:
            log.append("LOVE TRAIN desviou o ataque inimigo!")
            damage_to_player = 0
        applied = min(player["hp"], max(0, damage_to_player))
        player["hp"] -= applied
        log.append(f"O inimigo causou {applied} de dano.")
        if player_stand.get("reflect") and applied:
            reflected = min(enemy["hp"], int(applied * 0.30))
            enemy["hp"] -= reflected
            if reflected:
                log.append(f"CALAMITY devolveu {reflected} de dano ao oponente.")
    elif player_stopped_time:
        log.append("O oponente não conseguiu responder.")

    if enemy["hp"] <= 0 and player["hp"] <= 0:
        log.append("Empate! Os dois lutadores foram derrotados.")
    elif enemy["hp"] <= 0:
        log.append(f"{enemy['stand']} foi derrotado.")
    elif player["hp"] <= 0:
        log.append(f"{player['stand']} foi derrotado.")
    return log
