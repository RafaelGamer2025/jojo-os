from __future__ import annotations

import random
import tkinter as tk
from tkinter import messagebox

from core.battle_system import STANDS, criar_lutador, turno_batalha


class BattleWindow:
    """Demonstração jogável de batalha por turnos entre dois Stands."""

    def __init__(self, master, username: str, player_stand: str):
        if player_stand not in STANDS:
            raise ValueError("Stand do jogador não reconhecido.")
        opponents = [name for name in STANDS if name != player_stand]
        self.enemy_stand = random.choice(opponents)
        self.player = criar_lutador(player_stand)
        self.enemy = criar_lutador(self.enemy_stand)
        self.turn = 0
        self.finished = False

        self.window = tk.Toplevel(master)
        self.window.title("JOJO-OS // BATALHA DE STANDS")
        self.window.geometry("720x560")
        self.window.minsize(600, 460)
        self.window.configure(bg="#101014")
        self.window.transient(master)

        tk.Label(
            self.window,
            text=f"⚔️ {username} — BATALHA DE STANDS",
            fg="#FFD700",
            bg="#101014",
            font=("Impact", 22),
        ).pack(pady=(18, 6))

        self.status = tk.Label(
            self.window,
            text="",
            fg="#FFFFFF",
            bg="#101014",
            font=("Consolas", 12),
            justify="center",
        )
        self.status.pack(pady=12)

        self.log = tk.Text(
            self.window,
            height=14,
            bg="#19191f",
            fg="#f2f2f2",
            font=("Consolas", 10),
            wrap=tk.WORD,
            state=tk.DISABLED,
        )
        self.log.pack(fill="both", expand=True, padx=18, pady=12)

        actions = tk.Frame(self.window, bg="#101014")
        actions.pack(pady=(0, 18))
        tk.Button(actions, text="LUTAR", width=16, command=self.play_turn).pack(side="left", padx=6)
        tk.Button(actions, text="FECHAR", width=12, command=self.window.destroy).pack(side="left", padx=6)
        self._refresh_status()
        self._append(f"{player_stand} encara {self.enemy_stand}.\nAperte LUTAR para avançar um turno.\n")

    def _refresh_status(self) -> None:
        self.status.config(
            text=(
                f"VOCÊ: {self.player['stand']} — HP {self.player['hp']}/100\n"
                f"OPONENTE: {self.enemy['stand']} — HP {self.enemy['hp']}/100"
            )
        )

    def _append(self, text: str) -> None:
        self.log.config(state=tk.NORMAL)
        self.log.insert(tk.END, text + ("\n" if not text.endswith("\n") else ""))
        self.log.see(tk.END)
        self.log.config(state=tk.DISABLED)

    def play_turn(self) -> None:
        if self.finished:
            return
        self.turn += 1
        events = turno_batalha(self.player, self.enemy)
        self._append(f"— TURNO {self.turn} —")
        for event in events:
            self._append(event)
        self._refresh_status()

        if self.player["hp"] <= 0 or self.enemy["hp"] <= 0:
            self.finished = True
            if self.enemy["hp"] <= 0 and self.player["hp"] > 0:
                outcome = "Vitória!"
            elif self.player["hp"] <= 0 and self.enemy["hp"] > 0:
                outcome = "Derrota!"
            else:
                outcome = "Empate!"
            self._append(outcome)
            messagebox.showinfo("Batalha encerrada", outcome, parent=self.window)
