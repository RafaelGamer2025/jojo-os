"""Pure desktop icon-grid calculations.

The module deliberately has no Tk dependency.  Persisted icon coordinates are
still represented as ``[x, y]`` pixel pairs, but every returned coordinate is
a top-left coordinate of a fixed grid slot.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from numbers import Real
from typing import Any

DEFAULT_WIDTH = 1000
DEFAULT_HEIGHT = 660
# Current Tk icon frames can request about 137 px on Linux; keep a visible
# gutter between them. The GUI also expands cells when a platform requests more.
DEFAULT_CELL_WIDTH = 150
DEFAULT_CELL_HEIGHT = 150
DEFAULT_ORIGIN_X = 50
DEFAULT_ORIGIN_Y = 50

Point = tuple[int, int]


def _as_dimension(value: Any, fallback: int) -> int:
    if isinstance(value, bool) or not isinstance(value, Real):
        return fallback
    try:
        if not math.isfinite(value):
            return fallback
    except (TypeError, ValueError, OverflowError):
        return fallback
    return max(0, int(value))


def _as_point(value: Any) -> Point | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return None
    if len(value) != 2:
        return None
    if any(isinstance(item, bool) or not isinstance(item, Real) for item in value):
        return None
    try:
        if not all(math.isfinite(item) for item in value):
            return None
    except (TypeError, ValueError, OverflowError):
        return None
    return int(value[0]), int(value[1])


@dataclass(frozen=True, slots=True)
class DesktopGrid:
    """A fixed-size grid clipped to the usable desktop/canvas dimensions.

    ``origin_x`` and ``origin_y`` are the first slot's top-left pixel.  Slots
    are returned row-major, which is also the tie-break order used whenever two
    candidates are equally close.
    """

    width: int = DEFAULT_WIDTH
    height: int = DEFAULT_HEIGHT
    cell_width: int = DEFAULT_CELL_WIDTH
    cell_height: int = DEFAULT_CELL_HEIGHT
    origin_x: int = DEFAULT_ORIGIN_X
    origin_y: int = DEFAULT_ORIGIN_Y

    def __post_init__(self) -> None:
        values = (
            self.width,
            self.height,
            self.cell_width,
            self.cell_height,
            self.origin_x,
            self.origin_y,
        )
        if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
            raise TypeError("As dimensões da grade devem ser inteiros.")
        if self.width < 0 or self.height < 0:
            raise ValueError("As dimensões da área devem ser não negativas.")
        if self.cell_width <= 0 or self.cell_height <= 0:
            raise ValueError("As células da grade devem ter dimensões positivas.")
        if self.origin_x < 0 or self.origin_y < 0:
            raise ValueError("A origem da grade deve ser não negativa.")

    @property
    def columns(self) -> int:
        return max(0, (self.width - self.origin_x) // self.cell_width)

    @property
    def rows(self) -> int:
        return max(0, (self.height - self.origin_y) // self.cell_height)

    @property
    def slot_count(self) -> int:
        return self.columns * self.rows

    @property
    def slots(self) -> tuple[Point, ...]:
        return tuple(
            (self.origin_x + column * self.cell_width, self.origin_y + row * self.cell_height)
            for row in range(self.rows)
            for column in range(self.columns)
        )

    def nearest_free_slot(
        self,
        point: Sequence[Real] | None,
        occupied: Iterable[Sequence[Real]] = (),
    ) -> Point | None:
        """Return the closest unused slot, with stable row/column tie breaks."""
        occupied_points = {
            parsed for raw in occupied if (parsed := _as_point(raw)) is not None
        }
        available = [slot for slot in self.slots if slot not in occupied_points]
        if not available:
            return None

        requested = _as_point(point) or available[0]
        return min(
            available,
            key=lambda slot: (
                (slot[0] - requested[0]) ** 2 + (slot[1] - requested[1]) ** 2,
                (slot[1] - self.origin_y) // self.cell_height,
                (slot[0] - self.origin_x) // self.cell_width,
            ),
        )

    def snap(self, point: Sequence[Real] | None) -> Point | None:
        """Return the nearest slot without considering occupancy."""
        return self.nearest_free_slot(point)


def grid_for_size(
    width: Real,
    height: Real,
    *,
    cell_width: int = DEFAULT_CELL_WIDTH,
    cell_height: int = DEFAULT_CELL_HEIGHT,
    origin_x: int = DEFAULT_ORIGIN_X,
    origin_y: int = DEFAULT_ORIGIN_Y,
) -> DesktopGrid:
    """Build a validated grid from a Tk-like width/height pair."""
    return DesktopGrid(
        width=_as_dimension(width, DEFAULT_WIDTH),
        height=_as_dimension(height, DEFAULT_HEIGHT),
        cell_width=cell_width,
        cell_height=cell_height,
        origin_x=origin_x,
        origin_y=origin_y,
    )


def slots_for_size(
    width: Real,
    height: Real,
    *,
    cell_width: int = DEFAULT_CELL_WIDTH,
    cell_height: int = DEFAULT_CELL_HEIGHT,
    origin_x: int = DEFAULT_ORIGIN_X,
    origin_y: int = DEFAULT_ORIGIN_Y,
) -> tuple[Point, ...]:
    """Return the row-major slots that fit in a given desktop area."""
    return grid_for_size(
        width,
        height,
        cell_width=cell_width,
        cell_height=cell_height,
        origin_x=origin_x,
        origin_y=origin_y,
    ).slots


def snap_to_slot(
    x: Real,
    y: Real,
    *,
    width: Real = DEFAULT_WIDTH,
    height: Real = DEFAULT_HEIGHT,
) -> Point:
    """Snap a pixel coordinate to the nearest slot in the default grid."""
    grid = grid_for_size(width, height)
    return grid.snap((x, y)) or (DEFAULT_ORIGIN_X, DEFAULT_ORIGIN_Y)


def choose_nearest_free_slot(
    point: Sequence[Real] | None,
    occupied: Iterable[Sequence[Real]],
    origin: Sequence[Real] | None,
    *,
    grid: DesktopGrid | None = None,
) -> Point:
    """Choose a drop slot or return the icon's original slot when full.

    Callers should omit the icon being dragged from ``occupied``.  When the
    requested cell differs from the origin, do not choose the origin merely
    because it is the closest free slot; prefer another free slot.  The origin
    remains the fallback when every other slot is unavailable.
    """
    active_grid = grid or DesktopGrid()
    occupied_points = tuple(occupied)
    original = active_grid.snap(origin)
    requested_slot = active_grid.snap(point)
    selected = active_grid.nearest_free_slot(point, occupied_points)
    if selected == original and requested_slot is not None and requested_slot != original:
        selected = active_grid.nearest_free_slot(
            point,
            (*occupied_points, original) if original is not None else occupied_points,
        )
    if selected is not None:
        return selected
    if original is not None:
        return original
    parsed_origin = _as_point(origin)
    return parsed_origin or (active_grid.origin_x, active_grid.origin_y)


def normalize_positions(
    positions: Mapping[str, Sequence[Real]] | Any,
    *,
    width: Real = DEFAULT_WIDTH,
    height: Real = DEFAULT_HEIGHT,
    order: Iterable[str] = (),
    grid: DesktopGrid | None = None,
) -> dict[str, list[int]]:
    """Normalize persisted pixel positions into unique, in-bounds slots.

    Keys listed in ``order`` are processed first.  All remaining string keys
    are processed lexicographically, making conflict resolution independent of
    JSON/SQLite insertion ordering.
    """
    if not isinstance(positions, Mapping):
        return {}

    active_grid = grid or grid_for_size(width, height)
    priority: dict[str, int] = {}
    for index, key in enumerate(order):
        if isinstance(key, str) and key not in priority:
            priority[key] = index

    valid: list[tuple[str, Point]] = []
    for key, raw_point in positions.items():
        if not isinstance(key, str):
            continue
        parsed = _as_point(raw_point)
        if parsed is not None:
            valid.append((key, parsed))

    default_priority = len(priority)
    valid.sort(key=lambda item: (priority.get(item[0], default_priority), item[0]))

    normalized: dict[str, list[int]] = {}
    for key, raw_point in valid:
        slot = active_grid.nearest_free_slot(raw_point, normalized.values())
        if slot is not None:
            normalized[key] = [slot[0], slot[1]]
    return normalized


def reflow_positions(
    positions: Mapping[str, Sequence[Real]] | Any,
    width: Real,
    height: Real,
    *,
    order: Iterable[str] = (),
    grid: DesktopGrid | None = None,
) -> dict[str, list[int]]:
    """Re-clamp and de-conflict positions after a desktop resize."""
    return normalize_positions(positions, width=width, height=height, order=order, grid=grid)


__all__ = [
    "DEFAULT_CELL_HEIGHT",
    "DEFAULT_CELL_WIDTH",
    "DEFAULT_HEIGHT",
    "DEFAULT_ORIGIN_X",
    "DEFAULT_ORIGIN_Y",
    "DEFAULT_WIDTH",
    "DesktopGrid",
    "choose_nearest_free_slot",
    "grid_for_size",
    "normalize_positions",
    "reflow_positions",
    "slots_for_size",
    "snap_to_slot",
]
