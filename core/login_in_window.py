# login_in_window.py
import hmac
import json
import math
import re
import tkinter as tk
from tkinter import messagebox, ttk

from core.security import (
    DB_FILE,
    SecurityStoreError,
    carregar_db_seguro,
    hash_password,
    salvar_db_seguro,
    verificar_senha,
)
from core.stand_awakening import choose_random_stand


class LoginWindow:
    def setup_login_ui(self):
        self._definir_tela_cheia(False, "450x600")
        self.win.unbind("<Escape>")
        self.win.unbind("<F11>")
        self.limpar_tela()

        tk.Label(self.win, text="LOGIN JOJO-OS", fg=self.theme.GOLD, bg="black",
                font=("Impact", 22)).pack(pady=40)

        tk.Label(self.win, text="USUÁRIO:", fg="white", bg="black").pack()
        self.ent_user = ttk.Entry(self.win)
        self.ent_user.pack(pady=5)

        tk.Label(self.win, text="SENHA:", fg="white", bg="black").pack()
        self.ent_pass = ttk.Entry(self.win, show="*")
        self.ent_pass.pack(pady=5)

        tk.Button(self.win, text="ENTRAR",
                command=self.check_login).pack(pady=20)

        tk.Button(self.win, text="CADASTRAR",
                command=self.tela_pergunta_inicial).pack(pady=10)

        tk.Button(self.win, text="ACESSO REQUIEM",
                command=self.tela_inserir_chave).pack(pady=5)

    def __init__(self, root, theme, on_success):
        self.root = root
        self.win = tk.Toplevel(root)
        self.theme = theme
        self.on_success = on_success
        self.fullscreen = False
        self.animation_after = None
        self.pending_stand = None
        self.pending_profile = "JOJO"
        self.pending_theme = {"bg": "#000000", "fg": "#FFD700", "accent": "#6A0DAD"}
        
        self.db_file = DB_FILE
        self.secret_file = DB_FILE.parent / "key_secret.json"
        self.config_file = DB_FILE.parent / "requiem_init.json"
        
        self.win.title("JOJO-OS // SISTEMA DE ACESSO")
        self.win.geometry("450x600")
        self.win.configure(bg="black")
        self.win.resizable(False, False)
        self.win.grab_set()

        # Lógica principal: Tem conta ou é a primeira vez?
        if not self.verificar_se_existem_usuarios():
            self.tela_pergunta_inicial() # Fluxo de criar conta
        else:
            self.setup_login_ui() # Fluxo de login normal

    def verificar_se_existem_usuarios(self):
        """Consulta o banco já validado; um erro de integridade nunca vira banco vazio."""
        try:
            data = carregar_db_seguro(self.db_file)
            return bool(data) or data.get("__hack_detected__") is True
        except (OSError, SecurityStoreError, ValueError):
            return True

    def limpar_tela(self):
        if self.animation_after is not None:
            try:
                self.win.after_cancel(self.animation_after)
            except tk.TclError:
                pass
            self.animation_after = None
        for widget in self.win.winfo_children():
            widget.destroy()

    # --- FLUXO DE CADASTRO (PRIMEIRO ACESSO) ---

    def tela_pergunta_inicial(self):
        self.pending_stand = None
        self.pending_profile = "JOJO"
        self.pending_theme = {"bg": "#000000", "fg": "#FFD700", "accent": "#6A0DAD"}
        self._definir_tela_cheia(True)
        self.limpar_tela()
        self.win.title("JOJO-OS // DESPERTAR DA ALMA")
        self.win.bind("<Escape>", self._alternar_tela_cheia)
        self.win.bind("<F11>", self._alternar_tela_cheia)

        content = tk.Frame(self.win, bg="#080610", padx=24, pady=24)
        content.pack(expand=True, fill="both")
        tk.Label(
            content,
            text="◆  CERIMÔNIA DE DESPERTAR  ◆",
            fg=self.theme.GOLD,
            bg="#080610",
            font=("Impact", 24),
        ).pack(pady=(20, 12))
        tk.Label(
            content,
            text="VOCÊ ACEITA A FLECHA QUE DESPERTA SUA ALMA?",
            fg="white",
            bg="#080610",
            font=("Impact", 30),
            wraplength=1000,
            justify="center",
        ).pack(pady=16)
        tk.Label(
            content,
            text="SIM: uma carta revela um Stand aleatório.\nNÃO: você segue sem Stand.\nQUERO SER UM HACKER: ativa o perfil visual CLEITON OS (sem privilégios administrativos).",
            fg="#C9C5D7",
            bg="#080610",
            font=("Courier New", 15),
            justify="center",
        ).pack(pady=10)

        button_row = tk.Frame(content, bg="#080610")
        button_row.pack(pady=24)
        choices = (
            ("SIM — DESPERTAR STAND", self.despertar_stand, "#6A0DAD"),
            ("NÃO — SEGUIR SEM STAND", self.registro_sem_stand, "#35333D"),
            ("QUERO SER UM HACKER", self.registro_hacker, "#003B00"),
        )
        for label, command, color in choices:
            tk.Button(
                button_row,
                text=label,
                command=command,
                width=25,
                height=3,
                bg=color,
                fg="white",
                activebackground=self.theme.GOLD,
                activeforeground="black",
                font=("Impact", 13),
                cursor="hand2",
                bd=0,
            ).pack(side="left", padx=10)

        tk.Button(
            content,
            text="ACESSO REQUIEM // CADASTRO ADMINISTRATIVO",
            command=self.tela_inserir_chave,
            bg="#17131D",
            fg=self.theme.GOLD,
            font=("Courier New", 10),
            cursor="hand2",
            bd=0,
        ).pack(pady=12)
        tk.Label(
            content,
            text="ESC sai da tela cheia • F11 alterna a tela cheia",
            fg="#77717F",
            bg="#080610",
            font=("Arial", 9),
        ).pack(side="bottom", pady=4)

    def _definir_tela_cheia(self, enabled, geometry="900x700"):
        self.fullscreen = bool(enabled)
        try:
            self.win.attributes("-fullscreen", self.fullscreen)
            if self.fullscreen:
                width = max(640, int(self.win.winfo_screenwidth()))
                height = max(480, int(self.win.winfo_screenheight()))
                self.win.geometry(f"{width}x{height}+0+0")
            else:
                self.win.geometry(geometry)
                self.win.resizable(False, False)
            self.win.lift()
        except tk.TclError:
            self.fullscreen = False
            self.win.geometry(geometry)

    def _alternar_tela_cheia(self, _event=None):
        self._definir_tela_cheia(not self.fullscreen, "900x700")
        return "break"

    def despertar_stand(self):
        stand = choose_random_stand()
        self.pending_stand = stand.name
        self.pending_profile = "JOJO"
        self.pending_theme = {"bg": "#080610", "fg": stand.color, "accent": stand.color}
        self.tela_animacao_carta(stand)

    def registro_sem_stand(self):
        self.pending_stand = None
        self.pending_profile = "JOJO"
        self.pending_theme = {"bg": "#000000", "fg": "#FFD700", "accent": "#6A0DAD"}
        self.tela_cadastro_usuario()

    def registro_hacker(self):
        self.pending_stand = None
        self.pending_profile = "CLEITON"
        self.pending_theme = {"bg": "#0D0208", "fg": "#00FF41", "accent": "#003B00"}
        self.tela_cadastro_usuario()

    def tela_animacao_carta(self, stand):
        self.limpar_tela()
        self.win.title("JOJO-OS // CARTA DE DESPERTAR")
        self.animation_canvas = tk.Canvas(
            self.win,
            bg="#080610",
            highlightthickness=0,
        )
        self.animation_canvas.pack(expand=True, fill="both")
        self.animation_message = tk.Label(
            self.win,
            text="A carta está sendo revelada...",
            fg=self.theme.GOLD,
            bg="#080610",
            font=("Courier New", 14),
        )
        self.animation_message.pack(pady=6)
        self.animation_continue = tk.Button(
            self.win,
            text="CONTINUAR PARA O CADASTRO",
            state="disabled",
            command=self.tela_cadastro_usuario,
            bg="#6A0DAD",
            fg="white",
            font=("Impact", 15),
            cursor="hand2",
        )
        self.animation_continue.pack(pady=(4, 18))
        self._animar_carta(stand, 0)

    def _animar_carta(self, stand, frame):
        canvas = self.animation_canvas
        if not canvas.winfo_exists():
            return
        canvas.delete("all")
        width = max(320, canvas.winfo_width())
        height = max(320, canvas.winfo_height())
        center_x = width / 2
        center_y = height / 2
        total_frames = 28
        angle = (frame / total_frames) * math.pi
        flip_width = max(10, int(220 * abs(math.cos(angle))))
        card_height = 360
        x1 = center_x - flip_width / 2
        x2 = center_x + flip_width / 2
        y1 = center_y - card_height / 2
        y2 = center_y + card_height / 2

        if frame < total_frames // 2:
            self._desenhar_fundo_carta(canvas, x1, y1, x2, y2)
        else:
            self._desenhar_frente_carta(canvas, stand, center_x, center_y, flip_width, card_height)

        if frame >= total_frames:
            self._desenhar_frente_carta(canvas, stand, center_x, center_y, 250, card_height)
            self.animation_message.configure(
                text=f"CARTA REVELADA: {(stand.arcana or 'DEUSES DO EGITO').upper()}  •  STAND: {stand.name.upper()}"
            )
            self.animation_continue.configure(state="normal")
            return
        self.animation_after = self.win.after(45, lambda: self._animar_carta(stand, frame + 1))

    @staticmethod
    def _desenhar_fundo_carta(canvas, x1, y1, x2, y2):
        canvas.create_rectangle(x1, y1, x2, y2, fill="#211631", outline="#D8B65A", width=4)
        canvas.create_oval(x1 + 12, y1 + 12, x2 - 12, y2 - 12, outline="#A887DF", width=2)
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        canvas.create_text(cx, cy, text="✦", fill="#F5D778", font=("Times New Roman", 56, "bold"))
        canvas.create_text(cx, y1 + 38, text="ARCANA", fill="#F5D778", font=("Courier New", 12, "bold"))

    def _desenhar_frente_carta(self, canvas, stand, cx, cy, card_width, card_height):
        half_width = max(7, card_width / 2)
        x1 = cx - half_width
        x2 = cx + half_width
        y1 = cy - card_height / 2
        y2 = cy + card_height / 2
        color = stand.color
        canvas.create_rectangle(x1, y1, x2, y2, fill="#F2E8CF", outline="#D8B65A", width=5)
        canvas.create_rectangle(x1 + 9, y1 + 9, x2 - 9, y2 - 9, outline="#412B55", width=2)
        if card_width < 60:
            return
        group_names = {"TAROT": "CARTA DO TARÔ", "EGYPTIAN": "DEUSES DO EGITO", "OTHER": "OUTRO STAND"}
        canvas.create_text(
            cx,
            y1 + 32,
            text=group_names.get(stand.group, "ARCANO"),
            fill="#412B55",
            font=("Courier New", 10, "bold"),
        )
        canvas.create_text(
            cx,
            y1 + 60,
            text=(stand.arcana or "PANTEÃO EGÍPCIO").upper(),
            fill="#211631",
            font=("Impact", 17),
        )
        art_center_y = cy - 5
        self._desenhar_simbolo(canvas, stand.symbol, cx, art_center_y, color)
        canvas.create_line(x1 + 20, y2 - 67, x2 - 20, y2 - 67, fill="#B79A57", width=2)
        canvas.create_text(
            cx,
            y2 - 42,
            text=stand.name.upper(),
            fill="#211631",
            font=("Impact", 17),
            width=max(120, card_width - 28),
        )

    @staticmethod
    def _desenhar_simbolo(canvas, symbol, cx, cy, color):
        if symbol == "sun":
            for index in range(16):
                angle = index * math.tau / 16
                canvas.create_line(
                    cx + math.cos(angle) * 42,
                    cy + math.sin(angle) * 42,
                    cx + math.cos(angle) * 70,
                    cy + math.sin(angle) * 70,
                    fill=color,
                    width=4,
                )
            canvas.create_oval(cx - 40, cy - 40, cx + 40, cy + 40, fill=color, outline="#412B55", width=3)
            canvas.create_oval(cx - 13, cy - 13, cx + 13, cy + 13, fill="#F2E8CF", outline="#412B55", width=2)
            return
        if symbol in {"sword", "anubis"}:
            canvas.create_polygon(cx, cy - 86, cx - 16, cy + 20, cx + 16, cy + 20, fill=color, outline="#211631", width=3)
            canvas.create_line(cx - 38, cy + 25, cx + 38, cy + 25, fill="#211631", width=6)
            canvas.create_line(cx, cy + 22, cx, cy + 72, fill="#211631", width=8)
            canvas.create_oval(cx - 12, cy + 66, cx + 12, cy + 90, fill="#D8B65A", outline="#211631", width=2)
            return
        if symbol in {"eye", "judgement", "priestess"}:
            canvas.create_oval(cx - 76, cy - 43, cx + 76, cy + 43, outline=color, width=8)
            canvas.create_oval(cx - 28, cy - 28, cx + 28, cy + 28, fill=color, outline="#211631", width=3)
            canvas.create_oval(cx - 8, cy - 8, cx + 8, cy + 8, fill="#F2E8CF", outline="#211631", width=1)
            return
        if symbol in {"void", "world", "moon", "shadow"}:
            canvas.create_oval(cx - 72, cy - 72, cx + 72, cy + 72, fill="#171422", outline=color, width=7)
            canvas.create_oval(cx - 42, cy - 42, cx + 42, cy + 42, outline="#D8B65A", width=3)
            canvas.create_text(cx, cy, text="✦", fill=color, font=("Times New Roman", 44, "bold"))
            return
        if symbol in {"bird", "fool"}:
            canvas.create_polygon(
                cx, cy - 68, cx - 82, cy - 16, cx - 26, cy - 6,
                cx - 52, cy + 68, cx, cy + 34, cx + 52, cy + 68,
                cx + 26, cy - 6, cx + 82, cy - 16,
                fill=color, outline="#211631", width=3,
            )
            canvas.create_oval(cx - 9, cy - 78, cx + 9, cy - 60, fill="#D8B65A", outline="#211631")
            return
        if symbol in {"flame", "magician"}:
            canvas.create_polygon(
                cx, cy - 92, cx - 18, cy - 30, cx - 56, cy - 8,
                cx - 42, cy + 62, cx, cy + 84, cx + 45, cy + 58,
                cx + 55, cy + 8, cx + 20, cy - 24,
                fill=color, outline="#211631", width=3,
            )
            canvas.create_polygon(cx, cy - 18, cx - 18, cy + 35, cx + 18, cy + 36, fill="#F2E8CF", outline="#D8B65A", width=2)
            return

        canvas.create_oval(cx - 68, cy - 68, cx + 68, cy + 68, fill="#211631", outline=color, width=7)
        canvas.create_polygon(
            cx, cy - 56, cx + 48, cy, cx, cy + 56, cx - 48, cy,
            fill=color, outline="#F2E8CF", width=3,
        )
        canvas.create_oval(cx - 12, cy - 12, cx + 12, cy + 12, fill="#F2E8CF", outline="#211631", width=2)


            # ✅ AGORA SIM A FUNÇÃO EXISTE
    def tela_inserir_chave(self):
        self._definir_tela_cheia(False, "450x600")
        self.win.unbind("<Escape>")
        self.win.unbind("<F11>")
        self.limpar_tela()
        tk.Label(self.win, text="PROVE SEU VALOR", fg=self.theme.GOLD, bg="black", font=("Impact", 18)).pack(pady=30)
                
        self.key_ent = ttk.Entry(self.win, show="*")
        self.key_ent.pack(pady=10)
        self.key_ent.focus_set()
                
            
        tk.Button(self.win, text="VERIFICAR", command=self.validar_chave).pack(pady=10)

    def validar_chave(self):
        if not self.secret_file.is_file():
            messagebox.showerror("Erro", "A chave de cadastro administrativo não foi configurada em data/key_secret.json.", parent=self.win)
            return
        try:
            payload = json.loads(self.secret_file.read_text(encoding="utf-8"))
            chave_real = payload.get("master_key", "") if isinstance(payload, dict) else ""
        except (OSError, json.JSONDecodeError):
            messagebox.showerror("Erro", "O arquivo da chave de cadastro está inválido.", parent=self.win)
            return
        if isinstance(chave_real, str) and hmac.compare_digest(self.key_ent.get(), chave_real):
            self.tela_cadastro_admin()
        else:
            messagebox.showerror("Acesso negado", "Chave incorreta.", parent=self.win)

    def tela_cadastro_admin(self):
        self._definir_tela_cheia(False, "450x600")
        self.win.unbind("<Escape>")
        self.win.unbind("<F11>")
        self.limpar_tela()

        tk.Label(self.win, text="CADASTRAR ADMIN", fg=self.theme.GOLD, bg="black",
                font=("Impact", 15)).pack(pady=20)

        tk.Label(self.win, text="USUÁRIO:", fg="white", bg="black").pack()
        self.reg_user = ttk.Entry(self.win)
        self.reg_user.pack(pady=5)

        tk.Label(self.win, text="SENHA:", fg="white", bg="black").pack()
        self.reg_pass = ttk.Entry(self.win, show="*")
        self.reg_pass.pack(pady=5)

        tk.Label(self.win, text="ESCOLHA SEU STAND (ADMIN):",
                fg="red", bg="black").pack(pady=10)

        # ✅ APENAS ADMIN
        stands_admin = {
            "Tusk ACT 4": {"bg": "#000000", "fg": "#00FFFF", "accent": "#FF0000"},
            "Whitesnake": {"bg": "#000000", "fg": "#FFFFFF", "accent": "#6A0DAD"},
            "Wonder of U": {"bg": "#000000", "fg": "#FFD700", "accent": "#8B0000"},
            "The World": {"bg": "#000000", "fg": "#FFD700", "accent": "#32CD32"},
            "D4C": {"bg": "#000000", "fg": "#FF1493", "accent": "#00008B"}
        }

        for nome, cores in stands_admin.items():
            tk.Button(
                self.win,
                text=nome,
                width=30,
                command=lambda n=nome, c=cores: self.finalizar_cadastro_admin(n, c)
            ).pack(pady=2)
    def garantir_pasta_db(self):
        self.db_file.parent.mkdir(parents=True, exist_ok=True)

    def finalizar_cadastro_admin(self, nome, cores):
        user = self.reg_user.get().strip().lower()
        pw = self.reg_pass.get().strip()
        if not self._validar_novas_credenciais(user, pw):
            return
        self._salvar_nova_conta(user, pw, nome, cores, "admin")

    def _validar_novas_credenciais(self, user, password):
        if not re.fullmatch(r"[a-z0-9_.-]{3,32}", user):
            messagebox.showerror("Cadastro", "O usuário deve ter 3–32 caracteres: letras, números, ponto, hífen ou sublinhado.", parent=self.win)
            return False
        if len(password) < 8:
            messagebox.showerror("Cadastro", "Use uma senha com pelo menos 8 caracteres.", parent=self.win)
            return False
        return True

    def _salvar_nova_conta(self, user, password, stand, colors, role):
        try:
            db = carregar_db_seguro(self.db_file)
            if db.get("__hack_detected__") is True:
                messagebox.showerror("Cadastro bloqueado", "A integridade do banco falhou. Restaure uma cópia confiável antes de cadastrar.", parent=self.win)
                return
            if user in db:
                messagebox.showerror("Cadastro", "Esse usuário já existe.", parent=self.win)
                return
            db[user] = {
                "password": hash_password(password),
                "role": role,
                "stand": stand,
                "theme_data": dict(colors) if isinstance(colors, dict) else {},
                "os_profile": self.pending_profile if self.pending_profile in {"JOJO", "CLEITON"} else "JOJO",
                "historico": [],
                "memoria": {},
                "xp": 0,
                "level": 1,
            }
            salvar_db_seguro(db, self.db_file)
        except (OSError, ValueError, SecurityStoreError) as exc:
            messagebox.showerror("Cadastro", f"Não foi possível salvar a conta: {exc}", parent=self.win)
            return
        messagebox.showinfo("Sucesso", "Conta criada. Agora faça login.", parent=self.win)
        self.setup_login_ui()
    def salvar_usuario(self, novo_db):
        if not isinstance(novo_db, dict) or len(novo_db) != 1:
            messagebox.showerror("Cadastro", "Dados de conta inválidos.", parent=self.win)
            return
        user, account = next(iter(novo_db.items()))
        try:
            db = carregar_db_seguro(self.db_file)
            if db.get("__hack_detected__") is True:
                messagebox.showerror("Cadastro bloqueado", "A integridade do banco falhou.", parent=self.win)
                return
            if user in db:
                messagebox.showerror("Cadastro", "Esse usuário já existe.", parent=self.win)
                return
            db[user] = account
            salvar_db_seguro(db, self.db_file)
        except (OSError, ValueError, SecurityStoreError) as exc:
            messagebox.showerror("Cadastro", f"Não foi possível salvar: {exc}", parent=self.win)
            return
        messagebox.showinfo("Sucesso", "Usuário administrativo criado. Faça login.", parent=self.win)
        self.setup_login_ui()

    # --- FLUXO DE LOGIN (QUANDO JÁ TEM CONTA) ---
    def tela_cadastro_usuario(self):
        self.limpar_tela()

        self.win.title("JOJO-OS // CRIAR USUÁRIO")
        background = self.pending_theme.get("bg", "#000000")
        accent = self.pending_theme.get("accent", self.theme.PURPLE)
        foreground = self.pending_theme.get("fg", self.theme.GOLD)
        tk.Label(
            self.win,
            text="CRIAR USUÁRIO",
            fg=foreground,
            bg=background,
            font=("Impact", 25),
        ).pack(pady=(35, 18))

        if self.pending_profile == "CLEITON":
            message = "PERFIL ESCOLHIDO: CLEITON OS // VISUAL HACKER"
        elif self.pending_stand:
            message = f"STAND DESPERTADO: {self.pending_stand}"
        else:
            message = "SEM STAND DESPERTADO — VOCÊ PODE CONTINUAR"
        tk.Label(
            self.win,
            text=message,
            fg=foreground,
            bg=background,
            font=("Courier New", 13, "bold"),
            wraplength=760,
            justify="center",
        ).pack(padx=20, pady=12)

        tk.Label(self.win, text="USUÁRIO:", fg="white", bg=background).pack(pady=(20, 0))
        self.new_user = ttk.Entry(self.win)
        self.new_user.pack(pady=8, ipadx=65, ipady=5)

        tk.Label(self.win, text="SENHA:", fg="white", bg=background).pack(pady=(12, 0))
        self.new_pass = ttk.Entry(self.win, show="*")
        self.new_pass.pack(pady=8, ipadx=65, ipady=5)
        tk.Button(
            self.win,
            text="CRIAR CONTA",
            command=lambda: self.finalizar_cadastro_usuario(self.pending_stand, self.pending_theme),
            bg=accent,
            fg="white",
            font=("Impact", 15),
            cursor="hand2",
            width=25,
        ).pack(pady=32)

    def check_login(self):
        try:
            db = carregar_db_seguro(self.db_file)
        except (OSError, SecurityStoreError, ValueError) as exc:
            messagebox.showerror("Erro", f"Não foi possível validar o banco: {exc}", parent=self.win)
            return

        if db.get("__hack_detected__") is True:
            messagebox.showerror("Erro", "A assinatura do banco não confere. Não continue o login nem tente reparar sobrescrevendo os dados; restaure um backup íntegro.", parent=self.win)
            return

        u = self.ent_user.get().lower().strip()
        p = self.ent_pass.get().strip()

        if not u or not p:
            messagebox.showerror("Login", "Informe usuário e senha.", parent=self.win)
            return

        if u not in db:
            messagebox.showerror("Erro", "Usuário não existe!", parent=self.win)
            return

        account = db[u]
        if not isinstance(account, dict):
            messagebox.showerror("Erro", "O registro desta conta está inválido.", parent=self.win)
            return
        valid, needs_upgrade = verificar_senha(account.get("password"), p)
        if not valid:
            messagebox.showerror("Erro", "Senha incorreta!", parent=self.win)
            return

        if needs_upgrade:
            account["password"] = hash_password(p)
            try:
                salvar_db_seguro(db, self.db_file)
            except (OSError, ValueError, SecurityStoreError) as exc:
                messagebox.showerror("Login", f"Senha validada, mas a migração segura falhou: {exc}", parent=self.win)
                return

        self.win.destroy()
        self.on_success(
            u,
            is_admin=account.get("role") == "admin",
            theme_data=account.get("theme_data") if isinstance(account.get("theme_data"), dict) else None,
            stand=account.get("stand") if isinstance(account.get("stand"), str) else None,
            os_profile=account.get("os_profile") if account.get("os_profile") in {"JOJO", "CLEITON"} else "JOJO",
        )
    def finalizar_cadastro_usuario(self, nome, cores):
        user = self.new_user.get().strip().lower()
        pw = self.new_pass.get().strip()
        if not self._validar_novas_credenciais(user, pw):
            return
        self._salvar_nova_conta(user, pw, nome, cores, "user")
