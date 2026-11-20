from __future__ import annotations

from typing import ClassVar


class Theme:
    JOJO: ClassVar[dict[str, str]] = {
        "bg": "#000000",
        "fg": "#FFD700",
        "accent": "#8A2BE2",
        "secondary": "#FF69B4",
        "display": "#1a1a1a",
    }
    HACKER: ClassVar[dict[str, str]] = {
        "bg": "#0D0208",
        "fg": "#00FF41",
        "accent": "#008F11",
        "secondary": "#003B00",
        "display": "#000000",
    }

    def __init__(self, mode: str = "HACKER"):
        self.set_theme(mode)

    def set_theme(self, mode: str):
        source = self.JOJO if mode.upper() == "JOJO" else self.HACKER
        self._current = dict(source)
        return self.current

    @property
    def current(self) -> dict[str, str]:
        return dict(self._current)
