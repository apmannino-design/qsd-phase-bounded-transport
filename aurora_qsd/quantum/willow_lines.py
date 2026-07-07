"""Willow willow_pink qubit line presets (from Cirq device grid)."""

from __future__ import annotations

from dataclasses import dataclass

try:
    import cirq
except ImportError:
    cirq = None  # type: ignore[assignment]

# Boundary row-0 line from original willow_pink echo JSON (worst real estate).
BOUNDARY_LINE = ((0, 6), (0, 7), (0, 8))

# Interior row-6 center line — 4-way connectivity, widest chip row.
INTERIOR_LINE = ((6, 5), (6, 6), (6, 7))

# Slightly offset interior alternative.
INTERIOR_CENTER = ((6, 6), (6, 7), (6, 8))


@dataclass(frozen=True)
class WillowLine:
    name: str
    coords: tuple[tuple[int, int], tuple[int, int], tuple[int, int]]
    description: str

    def qubits(self) -> tuple:
        _require_cirq()
        return tuple(cirq.GridQubit(r, c) for r, c in self.coords)

    def labels(self) -> list[str]:
        return [f"q({r},{c})" for r, c in self.coords]

    @property
    def target_index(self) -> int:
        return 1


LINES = {
    "boundary": WillowLine(
        "boundary",
        BOUNDARY_LINE,
        "Row 0 edge — original echo JSON line (low connectivity)",
    ),
    "interior": WillowLine(
        "interior",
        INTERIOR_LINE,
        "Row 6 center — recommended interior line",
    ),
    "interior_center": WillowLine(
        "interior_center",
        INTERIOR_CENTER,
        "Row 6 offset — alternative interior line",
    ),
}


def _require_cirq() -> None:
    if cirq is None:
        raise ImportError("cirq required. pip install cirq cirq-google")


def get_line(name: str = "interior") -> WillowLine:
    if name not in LINES:
        raise ValueError(f"unknown line {name!r}; choose from {list(LINES)}")
    return LINES[name]


def validate_on_device(line: WillowLine, device) -> bool:
    qset = device.metadata.qubit_set
    return all(q in qset for q in line.qubits())
