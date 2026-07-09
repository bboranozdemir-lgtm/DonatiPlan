from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from .models import CutDemand, OptimizationResult, StockPiece
from .optimizer import BranchAndBoundCutOptimizer, CpSatCutOptimizer, GreedyCutOptimizer


class OptimizationMode(StrEnum):
    AUTO = "auto"
    EXACT = "exact"
    ADVANCED = "advanced"
    FAST = "fast"


@dataclass(frozen=True, slots=True)
class OptimizationRun:
    result: OptimizationResult
    requested_mode: OptimizationMode
    solver_used: OptimizationMode
    piece_count: int


class OptimizationService:
    """Stable application boundary shared by future API and import jobs."""

    def __init__(
        self,
        exact_item_limit: int = 32,
        stock_length_mm: int = 12_000,
        min_reusable_mm: int = 1_000,
        kerf_mm: int = 0,
        max_piece_limit: int = 500,
    ) -> None:
        self.fast = GreedyCutOptimizer(stock_length_mm, min_reusable_mm, kerf_mm)
        self.exact = BranchAndBoundCutOptimizer(
            stock_length_mm,
            min_reusable_mm,
            kerf_mm,
            max_items=exact_item_limit,
        )
        self.advanced = CpSatCutOptimizer(
            stock_length_mm,
            min_reusable_mm,
            kerf_mm,
        )
        self.exact_item_limit = exact_item_limit
        self.max_piece_limit = max_piece_limit

    def run(
        self,
        demands: Iterable[CutDemand],
        remnants: Iterable[StockPiece] = (),
        mode: OptimizationMode = OptimizationMode.AUTO,
    ) -> OptimizationRun:
        demand_list = list(demands)
        remnant_list = list(remnants)
        piece_count = sum(demand.quantity for demand in demand_list)
        if piece_count > self.max_piece_limit:
            raise ValueError(
                f"optimization limit is {self.max_piece_limit} pieces; received {piece_count}"
            )

        solver_mode = mode
        if mode == OptimizationMode.AUTO:
            solver_mode = (
                OptimizationMode.EXACT
                if piece_count <= self.exact_item_limit
                else OptimizationMode.ADVANCED
            )

        if solver_mode == OptimizationMode.EXACT:
            solver = self.exact
        elif solver_mode == OptimizationMode.ADVANCED:
            solver = self.advanced
        else:
            solver = self.fast
        result = solver.optimize(demand_list, remnant_list)
        return OptimizationRun(result, mode, solver_mode, piece_count)
