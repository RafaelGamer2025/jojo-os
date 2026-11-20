"""Small, deterministic helpers for short Tk visual effects."""

from __future__ import annotations

import colorsys
import math
from numbers import Real


def invert_rgb(rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    """Return the 8-bit RGB negative of a three-channel color."""
    if not isinstance(rgb, tuple) or len(rgb) != 3:
        raise ValueError("RGB precisa ter exatamente três canais.")
    if any(
        isinstance(channel, bool)
        or not isinstance(channel, int)
        or not 0 <= channel <= 255
        for channel in rgb
    ):
        raise ValueError("Cada canal RGB precisa ser um inteiro entre 0 e 255.")
    return tuple(255 - channel for channel in rgb)


def expanding_circle_radii(
    elapsed_seconds: Real,
    duration_seconds: Real,
    maximum_radius: Real,
    count: int = 3,
) -> tuple[int, ...]:
    """Return evenly phased radii that grow and repeat during the effect."""
    values = (elapsed_seconds, duration_seconds, maximum_radius)
    if any(isinstance(value, bool) or not isinstance(value, Real) for value in values):
        raise ValueError("Os valores da animação precisam ser numéricos.")
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Os valores da animação precisam ser finitos.")
    if duration_seconds <= 0 or maximum_radius < 0:
        raise ValueError("Duração deve ser positiva e raio não pode ser negativo.")
    if isinstance(count, bool) or not isinstance(count, int) or count < 1 or count > 12:
        raise ValueError("A quantidade de círculos deve ficar entre 1 e 12.")

    progress = (elapsed_seconds % duration_seconds) / duration_seconds
    limit = int(maximum_radius)
    return tuple(
        round(limit * ((progress + index / count) % 1.0))
        for index in range(count)
    )


def maximum_circle_radius(width: Real, height: Real) -> int:
    """Return the centered radius needed to cover every corner of a rectangle."""
    if any(
        isinstance(value, bool)
        or not isinstance(value, Real)
        or not math.isfinite(value)
        for value in (width, height)
    ):
        raise ValueError("Largura e altura precisam ser números finitos.")
    if width <= 0 or height <= 0:
        raise ValueError("Largura e altura precisam ser positivas.")
    return math.ceil(math.hypot(width / 2, height / 2))


def expanding_circle_radius(
    elapsed_seconds: Real,
    expansion_seconds: Real,
    maximum_radius: Real,
) -> int:
    """Return one monotonically expanding radius, clamped at the full-window size."""
    values = (elapsed_seconds, expansion_seconds, maximum_radius)
    if any(isinstance(value, bool) or not isinstance(value, Real) for value in values):
        raise ValueError("Os valores da animação precisam ser numéricos.")
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Os valores da animação precisam ser finitos.")
    if expansion_seconds <= 0 or maximum_radius < 0:
        raise ValueError("A duração precisa ser positiva e o raio não pode ser negativo.")
    progress = min(1.0, max(0.0, elapsed_seconds / expansion_seconds))
    return round(maximum_radius * progress)


def negative_circle_frame(image, radius: Real):
    """Return a screenshot copy with only the centered circular area color-inverted."""
    from PIL import Image, ImageDraw, ImageOps

    if not isinstance(image, Image.Image):
        raise TypeError("A imagem-base precisa ser uma imagem Pillow.")
    if (
        isinstance(radius, bool)
        or not isinstance(radius, Real)
        or not math.isfinite(radius)
        or radius < 0
    ):
        raise ValueError("O raio precisa ser um número finito não negativo.")

    base = image.convert("RGB")
    negative = ImageOps.invert(base)
    mask = Image.new("L", base.size, 0)
    width, height = base.size
    center_x, center_y = width / 2, height / 2
    ImageDraw.Draw(mask).ellipse(
        (center_x - radius, center_y - radius, center_x + radius, center_y + radius),
        fill=255,
    )
    return Image.composite(negative, base, mask)


def psychedelic_palette(elapsed_seconds: Real) -> tuple[str, str, str]:
    """Return a readable dark background, bright foreground and accent."""
    if (
        isinstance(elapsed_seconds, bool)
        or not isinstance(elapsed_seconds, Real)
        or not math.isfinite(elapsed_seconds)
    ):
        raise ValueError("O tempo da animação precisa ser finito.")

    hue = (elapsed_seconds * 0.17) % 1.0

    def color_at(offset: float, saturation: float, value: float) -> str:
        red, green, blue = colorsys.hsv_to_rgb((hue + offset) % 1.0, saturation, value)
        channels = tuple(round(channel * 255) for channel in (red, green, blue))
        return f"#{channels[0]:02X}{channels[1]:02X}{channels[2]:02X}"

    background = color_at(0.0, 0.82, 0.13)
    foreground = color_at(0.5, 0.38, 1.0)
    accent = color_at(0.72, 0.92, 1.0)
    return background, foreground, accent
