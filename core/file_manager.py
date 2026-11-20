from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext, simpledialog

from core.workspace import (
    WORKSPACE_DIR,
    ensure_workspace,
    resolve_workspace_path,
    validate_filename,
)

MAX_PREVIEW_BYTES = 1_000_000


class FileManager:
    """Gerenciador limitado a data/workspace; não navega pelo disco do host."""

    def __init__(self, master, workspace: str | Path | None = None):
        self.root = tk.Toplevel(master)
        self.root.title("JOJO-OS // MEUS ARQUIVOS")
        self.root.geometry("760x520")
        self.root.minsize(560, 360)
        self.root.configure(bg="#101014")

        self.workspace = ensure_workspace(workspace or WORKSPACE_DIR)
        self.current_path = self.workspace
        self.entries: list[Path] = []

        self.path_label = tk.Label(
            self.root,
            text="",
            bg="#101014",
            fg="#FFD700",
            anchor="w",
            font=("Consolas", 10),
        )
        self.path_label.pack(fill="x", padx=14, pady=(14, 6))

        toolbar = tk.Frame(self.root, bg="#101014")
        toolbar.pack(fill="x", padx=14, pady=6)
        tk.Button(toolbar, text="Voltar", command=self.voltar).pack(side="left")
        tk.Button(toolbar, text="Novo .txt", command=self.novo_txt).pack(side="left", padx=6)
        tk.Button(toolbar, text="Excluir arquivo", command=self.deletar).pack(side="left")
        tk.Button(toolbar, text="Atualizar", command=self.atualizar).pack(side="right")

        self.listbox = tk.Listbox(
            self.root,
            bg="#19191f",
            fg="#f2f2f2",
            selectbackground="#5f2aa6",
            font=("Consolas", 11),
            activestyle="none",
        )
        self.listbox.pack(fill="both", expand=True, padx=14, pady=(6, 14))
        self.listbox.bind("<Double-Button-1>", self.abrir_selecionado)
        self.atualizar()

    def _relative_path(self, path: Path) -> str:
        return "." if path == self.workspace else str(path.relative_to(self.workspace))

    def atualizar(self) -> None:
        try:
            self.current_path = resolve_workspace_path(self.workspace, self.current_path)
            if not self.current_path.is_dir():
                self.current_path = self.workspace
            self.path_label.config(text=f"Workspace seguro: /{self._relative_path(self.current_path)}")
            self.entries = []
            self.listbox.delete(0, tk.END)

            children = sorted(
                (p for p in self.current_path.iterdir() if not p.is_symlink()),
                key=lambda p: (not p.is_dir(), p.name.casefold()),
            )
            for child in children:
                try:
                    safe_child = resolve_workspace_path(self.workspace, child)
                except ValueError:
                    continue
                self.entries.append(safe_child)
                marker = "[PASTA]" if safe_child.is_dir() else "[ARQUIVO]"
                self.listbox.insert(tk.END, f"{marker} {safe_child.name}")
        except OSError as exc:
            messagebox.showerror("Arquivos", f"Não foi possível listar o workspace: {exc}", parent=self.root)

    def _selected_path(self) -> Path | None:
        selected = self.listbox.curselection()
        if not selected:
            return None
        index = int(selected[0])
        if index >= len(self.entries):
            return None
        try:
            return resolve_workspace_path(self.workspace, self.entries[index])
        except ValueError:
            messagebox.showerror("Caminho bloqueado", "Esse item aponta para fora do workspace.", parent=self.root)
            return None

    def abrir_selecionado(self, _event=None) -> None:
        path = self._selected_path()
        if path is None:
            return
        if path.is_dir():
            self.current_path = path
            self.atualizar()
            return
        if not path.is_file():
            messagebox.showwarning("Arquivo", "O item não está disponível.", parent=self.root)
            return
        if path.stat().st_size > MAX_PREVIEW_BYTES:
            messagebox.showwarning("Arquivo grande", "A prévia aceita arquivos de texto de até 1 MB.", parent=self.root)
            return
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            messagebox.showinfo("Prévia indisponível", "Só é possível abrir arquivos de texto UTF-8 no gerenciador.", parent=self.root)
            return

        preview = tk.Toplevel(self.root)
        preview.title(path.name)
        preview.geometry("700x460")
        text = scrolledtext.ScrolledText(preview, wrap=tk.WORD, font=("Consolas", 10))
        text.pack(fill="both", expand=True, padx=10, pady=10)
        text.insert("1.0", content)
        text.config(state=tk.DISABLED)

    def voltar(self) -> None:
        if self.current_path == self.workspace:
            return
        parent = self.current_path.parent
        self.current_path = parent if parent.is_relative_to(self.workspace) else self.workspace
        self.atualizar()

    def deletar(self) -> None:
        path = self._selected_path()
        if path is None:
            messagebox.showinfo("Excluir", "Selecione um arquivo primeiro.", parent=self.root)
            return
        if path.is_dir():
            messagebox.showwarning("Excluir", "A exclusão de pastas está desativada.", parent=self.root)
            return
        if not path.is_file():
            return
        if not messagebox.askyesno("Confirmar exclusão", f"Excluir {path.name} do workspace?", parent=self.root):
            return
        try:
            resolve_workspace_path(self.workspace, path).unlink()
            self.atualizar()
        except (OSError, ValueError) as exc:
            messagebox.showerror("Excluir", f"Não foi possível excluir o arquivo: {exc}", parent=self.root)

    def novo_txt(self) -> None:
        raw_name = simpledialog.askstring("Novo arquivo", "Nome do arquivo .txt:", initialvalue="novo_arquivo.txt", parent=self.root)
        if raw_name is None:
            return
        try:
            name = validate_filename(raw_name)
            if not name.lower().endswith(".txt"):
                name += ".txt"
            path = resolve_workspace_path(self.workspace, self.current_path / name)
            with path.open("x", encoding="utf-8") as new_file:
                new_file.write("")
        except FileExistsError:
            messagebox.showwarning("Novo arquivo", "Já existe um arquivo com esse nome.", parent=self.root)
            return
        except (OSError, ValueError) as exc:
            messagebox.showerror("Novo arquivo", str(exc), parent=self.root)
            return
        self.atualizar()
