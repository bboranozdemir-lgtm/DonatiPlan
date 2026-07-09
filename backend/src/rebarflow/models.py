from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class StockSource(StrEnum):
    NEW = "new"
    REMNANT = "remnant"


@dataclass(frozen=True, slots=True)
class CutDemand:
    """One bar mark and its required quantity.

    Lengths are stored as integer millimetres to avoid floating-point errors.
    """

    mark: str
    diameter_mm: int
    length_mm: int
    quantity: int
    phase: int = 0

    def __post_init__(self) -> None:
        if not self.mark.strip():
            raise ValueError("mark cannot be empty")
        if self.diameter_mm <= 0 or self.length_mm <= 0 or self.quantity <= 0:
            raise ValueError("diameter, length and quantity must be positive")
        if self.phase < 0:
            raise ValueError("phase cannot be negative")


@dataclass(frozen=True, slots=True)
class StockPiece:
    id: str
    diameter_mm: int
    length_mm: int
    source: StockSource = StockSource.REMNANT

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("stock id cannot be empty")
        if self.diameter_mm <= 0 or self.length_mm <= 0:
            raise ValueError("diameter and length must be positive")


@dataclass(frozen=True, slots=True)
class CutItem:
    mark: str
    length_mm: int
    phase: int


@dataclass(slots=True)
class CutPattern:
    stock: StockPiece
    cuts: list[CutItem] = field(default_factory=list)
    remaining_mm: int = 0
    kerf_loss_mm: int = 0

    @property
    def used_mm(self) -> int:
        return sum(item.length_mm for item in self.cuts)


@dataclass(frozen=True, slots=True)
class OptimizationResult:
    patterns: tuple[CutPattern, ...]
    demand_length_mm: int
    purchased_length_mm: int
    remnant_input_used_mm: int
    reusable_output_mm: int
    scrap_output_mm: int
    kerf_loss_mm: int

    @property
    def purchased_bar_count(self) -> int:
        return sum(1 for pattern in self.patterns if pattern.stock.source == StockSource.NEW)

    @property
    def purchase_waste_rate(self) -> float:
        return self.waste_rate

    @property
    def remnant_source_used_mm(self) -> int:
        return sum(
            pattern.stock.length_mm
            for pattern in self.patterns
            if pattern.stock.source == StockSource.REMNANT and pattern.cuts
        )

    @property
    def used_source_length_mm(self) -> int:
        return self.purchased_length_mm + self.remnant_source_used_mm

    @property
    def new_stock_waste_mm(self) -> int:
        return sum(
            pattern.remaining_mm
            for pattern in self.patterns
            if pattern.stock.source == StockSource.NEW
        )

    @property
    def total_waste_mm(self) -> int:
        return sum(pattern.remaining_mm for pattern in self.patterns)

    @property
    def new_stock_waste_rate(self) -> float:
        if self.purchased_length_mm == 0:
            return 0.0
        return self.new_stock_waste_mm / self.purchased_length_mm

    @property
    def waste_rate(self) -> float:
        if self.used_source_length_mm == 0:
            return 0.0
        return self.total_waste_mm / self.used_source_length_mm

    @property
    def real_scrap_mm(self) -> int:
        return self.scrap_output_mm

    @property
    def real_scrap_rate(self) -> float:
        if self.used_source_length_mm == 0:
            return 0.0
        return self.real_scrap_mm / self.used_source_length_mm
