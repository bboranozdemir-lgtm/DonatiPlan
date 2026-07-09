from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from math import ceil

from ortools.sat.python import cp_model

from .models import (
    CutDemand,
    CutItem,
    CutPattern,
    OptimizationResult,
    StockPiece,
    StockSource,
)


class GreedyCutOptimizer:
    """Deterministic best-fit-decreasing baseline optimizer.

    The implementation is intentionally dependency-free. It provides a tested
    baseline for comparing future integer-programming and heuristic solvers.
    Different diameters are never mixed, and existing remnants are considered
    before purchasing a new stock bar.
    """

    def __init__(
        self,
        stock_length_mm: int = 12_000,
        min_reusable_mm: int = 1_000,
        kerf_mm: int = 0,
    ) -> None:
        if stock_length_mm <= 0 or min_reusable_mm < 0 or kerf_mm < 0:
            raise ValueError("invalid stock or minimum reusable length")
        self.stock_length_mm = stock_length_mm
        self.min_reusable_mm = min_reusable_mm
        self.kerf_mm = kerf_mm

    def optimize(
        self,
        demands: Iterable[CutDemand],
        remnants: Iterable[StockPiece] = (),
    ) -> OptimizationResult:
        demand_list = list(demands)
        remnant_list = list(remnants)
        if not demand_list:
            raise ValueError("at least one demand is required")

        expanded: dict[int, list[CutItem]] = defaultdict(list)
        demand_length = 0
        for demand in demand_list:
            if demand.length_mm > self.stock_length_mm:
                raise ValueError(
                    f"{demand.mark}: required length exceeds standard stock length"
                )
            for _ in range(demand.quantity):
                expanded[demand.diameter_mm].append(
                    CutItem(demand.mark, demand.length_mm, demand.phase)
                )
                demand_length += demand.length_mm

        available: dict[int, list[CutPattern]] = defaultdict(list)
        for piece in remnant_list:
            available[piece.diameter_mm].append(
                CutPattern(stock=piece, remaining_mm=piece.length_mm)
            )

        all_patterns: list[CutPattern] = []
        for diameter in sorted(expanded):
            all_patterns.extend(
                self._solve_diameter_heuristic(
                    diameter,
                    expanded[diameter],
                    available[diameter],
                )
            )

        used_patterns = [pattern for pattern in all_patterns if pattern.cuts]
        purchased_length = sum(
            pattern.stock.length_mm
            for pattern in used_patterns
            if pattern.stock.source == StockSource.NEW
        )
        remnant_used = sum(
            pattern.used_mm
            for pattern in used_patterns
            if pattern.stock.source == StockSource.REMNANT
        )
        reusable_output = sum(
            pattern.remaining_mm
            for pattern in used_patterns
            if pattern.remaining_mm >= self.min_reusable_mm
        )
        scrap_output = sum(
            pattern.remaining_mm
            for pattern in used_patterns
            if pattern.remaining_mm < self.min_reusable_mm
        )

        return OptimizationResult(
            patterns=tuple(used_patterns),
            demand_length_mm=demand_length,
            purchased_length_mm=purchased_length,
            remnant_input_used_mm=remnant_used,
            reusable_output_mm=reusable_output,
            scrap_output_mm=scrap_output,
            kerf_loss_mm=sum(pattern.kerf_loss_mm for pattern in used_patterns),
        )

    def _solve_diameter_heuristic(
        self,
        diameter: int,
        items: list[CutItem],
        remnants: list[CutPattern],
    ) -> list[CutPattern]:
        strategies = (
            _PlacementStrategy("best-fit-desc", "desc", "best_fit"),
            _PlacementStrategy("best-fit-asc", "asc", "best_fit"),
            _PlacementStrategy("phase-desc", "phase_desc", "best_fit"),
            _PlacementStrategy("phase-asc", "phase_asc", "best_fit"),
            _PlacementStrategy("least-scrap-desc", "desc", "least_scrap"),
            _PlacementStrategy("long-remnant-desc", "desc", "preserve_long"),
            _PlacementStrategy("first-fit-desc", "desc", "first_fit"),
        )
        best_bins: list[_SearchBin] | None = None
        best_score: tuple[int, int, int, int, int] | None = None
        for strategy in strategies:
            candidate = self._run_placement_strategy(diameter, items, remnants, strategy)
            score = _score_bins(candidate, self.min_reusable_mm)
            if best_score is None or score < best_score:
                best_score = score
                best_bins = candidate
        if best_bins is None:
            raise RuntimeError("heuristic solver failed to produce a feasible plan")
        return [
            CutPattern(
                stock=bin_.stock,
                cuts=list(bin_.cuts),
                remaining_mm=bin_.remaining_mm,
                kerf_loss_mm=bin_.kerf_loss_mm,
            )
            for bin_ in best_bins
            if bin_.cuts
        ]

    def _run_placement_strategy(
        self,
        diameter: int,
        items: list[CutItem],
        remnants: list[CutPattern],
        strategy: _PlacementStrategy,
    ) -> list[_SearchBin]:
        ordered_items = sorted(items, key=self._item_sort_key(strategy.item_order))
        bins = [
            _SearchBin(
                stock=pattern.stock,
                remaining_mm=pattern.stock.length_mm,
                cuts=[],
                kerf_loss_mm=0,
            )
            for pattern in sorted(
                remnants,
                key=lambda pattern: (-pattern.stock.length_mm, pattern.stock.id),
            )
        ]
        new_counter = 0

        for item in ordered_items:
            required_mm = item.length_mm + self.kerf_mm
            candidates = [
                (bin_index, bin_)
                for bin_index, bin_ in enumerate(bins)
                if bin_.remaining_mm >= required_mm
            ]
            if candidates:
                chosen_index, chosen = min(
                    candidates,
                    key=lambda pair: self._bin_choice_key(pair[0], pair[1], required_mm, strategy.bin_choice),
                )
            else:
                new_counter += 1
                chosen = _SearchBin(
                    stock=StockPiece(
                        id=f"NEW-{diameter}-H{new_counter:05d}",
                        diameter_mm=diameter,
                        length_mm=self.stock_length_mm,
                        source=StockSource.NEW,
                    ),
                    remaining_mm=self.stock_length_mm,
                    cuts=[],
                    kerf_loss_mm=0,
                )
                bins.append(chosen)
                chosen_index = len(bins) - 1

            del chosen_index
            chosen.cuts.append(item)
            chosen.remaining_mm -= required_mm
            chosen.kerf_loss_mm += self.kerf_mm
        return bins

    def _item_sort_key(self, order: str):
        if order == "asc":
            return lambda item: (item.length_mm, item.phase, item.mark)
        if order == "phase_desc":
            return lambda item: (item.phase, -item.length_mm, item.mark)
        if order == "phase_asc":
            return lambda item: (item.phase, item.length_mm, item.mark)
        return lambda item: (-item.length_mm, item.phase, item.mark)

    def _bin_choice_key(
        self,
        index: int,
        bin_: _SearchBin,
        required_mm: int,
        choice: str,
    ) -> tuple[int, int, int, int, str]:
        post_remaining = bin_.remaining_mm - required_mm
        is_new = int(bin_.stock.source == StockSource.NEW)
        if choice == "first_fit":
            return (is_new, index, 0, 0, bin_.stock.id)
        if choice == "least_scrap":
            real_scrap = post_remaining if 0 < post_remaining < self.min_reusable_mm else 0
            reusable_penalty = 0 if post_remaining == 0 or post_remaining >= self.min_reusable_mm else 1
            return (real_scrap, reusable_penalty, post_remaining, is_new, bin_.stock.id)
        if choice == "preserve_long":
            scrap_penalty = 1 if 0 < post_remaining < self.min_reusable_mm else 0
            long_reusable = post_remaining if post_remaining >= self.min_reusable_mm else 0
            return (scrap_penalty, -long_reusable, post_remaining, is_new, bin_.stock.id)
        return (post_remaining, is_new, index, 0, bin_.stock.id)


@dataclass(slots=True)
class _SearchBin:
    stock: StockPiece
    remaining_mm: int
    cuts: list[CutItem]
    kerf_loss_mm: int = 0


@dataclass(frozen=True, slots=True)
class _PlacementStrategy:
    name: str
    item_order: str
    bin_choice: str


def _score_bins(
    bins: Iterable[_SearchBin],
    min_reusable_mm: int,
) -> tuple[int, int, int, int, int]:
    """Return the canonical optimization score.

    Lower tuples are better:
    1. new stock bar count
    2. true scrap below the reusable threshold
    3. total remaining waste
    4. reusable remnant piece count
    5. longest reusable remnant, negated so a longer single remnant wins
    """

    used = [bin_ for bin_ in bins if bin_.cuts]
    purchased = int(sum(bin_.stock.source == StockSource.NEW for bin_ in used))
    real_scrap = sum(
        bin_.remaining_mm
        for bin_ in used
        if 0 < bin_.remaining_mm < min_reusable_mm
    )
    total_waste = sum(bin_.remaining_mm for bin_ in used)
    reusable_lengths = [
        bin_.remaining_mm
        for bin_ in used
        if bin_.remaining_mm >= min_reusable_mm and bin_.remaining_mm > 0
    ]
    return (
        purchased,
        real_scrap,
        total_waste,
        len(reusable_lengths),
        -max(reusable_lengths, default=0),
    )


class BranchAndBoundCutOptimizer(GreedyCutOptimizer):
    """Exact minimum-new-bar solver for bounded problem sizes.

    The primary objective is to minimize purchased stock bars. Ties are broken
    by true scrap below ``min_reusable_mm``, then total remaining waste, then a
    smaller count of longer reusable remnants. It is deliberately bounded
    because exact bin packing is NP-hard; larger jobs should use an industrial
    MIP/CP-SAT solver.
    """

    def __init__(
        self,
        stock_length_mm: int = 12_000,
        min_reusable_mm: int = 1_000,
        kerf_mm: int = 0,
        max_items: int = 32,
    ) -> None:
        super().__init__(stock_length_mm, min_reusable_mm, kerf_mm)
        if max_items <= 0:
            raise ValueError("max_items must be positive")
        self.max_items = max_items

    def optimize(
        self,
        demands: Iterable[CutDemand],
        remnants: Iterable[StockPiece] = (),
    ) -> OptimizationResult:
        demand_list = list(demands)
        remnant_list = list(remnants)
        item_count = sum(demand.quantity for demand in demand_list)
        if item_count > self.max_items:
            raise ValueError(
                f"exact solver limit is {self.max_items} pieces; received {item_count}"
            )
        if not demand_list:
            raise ValueError("at least one demand is required")

        by_diameter: dict[int, list[CutItem]] = defaultdict(list)
        for demand in demand_list:
            if demand.length_mm > self.stock_length_mm:
                raise ValueError(
                    f"{demand.mark}: required length exceeds standard stock length"
                )
            by_diameter[demand.diameter_mm].extend(
                CutItem(demand.mark, demand.length_mm, demand.phase)
                for _ in range(demand.quantity)
            )

        remnants_by_diameter: dict[int, list[StockPiece]] = defaultdict(list)
        for remnant in remnant_list:
            remnants_by_diameter[remnant.diameter_mm].append(remnant)

        patterns: list[CutPattern] = []
        for diameter in sorted(by_diameter):
            diameter_patterns = self._solve_diameter(
                diameter,
                by_diameter[diameter],
                remnants_by_diameter[diameter],
            )
            patterns.extend(diameter_patterns)

        return self._build_result(patterns, demand_list)

    def _solve_diameter(
        self,
        diameter: int,
        items: list[CutItem],
        remnants: list[StockPiece],
    ) -> list[CutPattern]:
        items = sorted(items, key=lambda item: (-item.length_mm, item.phase, item.mark))
        initial_bins = [
            _SearchBin(piece, piece.length_mm, [], 0)
            for piece in sorted(remnants, key=lambda piece: (-piece.length_mm, piece.id))
        ]

        greedy_demands = [
            CutDemand(
                mark=f"EXACT-{index}",
                diameter_mm=diameter,
                length_mm=item.length_mm,
                quantity=1,
                phase=item.phase,
            )
            for index, item in enumerate(items)
        ]
        greedy = super().optimize(greedy_demands, remnants)
        best_bins: list[_SearchBin] | None = [
            _SearchBin(
                pattern.stock,
                pattern.remaining_mm,
                list(pattern.cuts),
                pattern.kerf_loss_mm,
            )
            for pattern in greedy.patterns
        ]
        best_score = self._score_patterns(best_bins)

        suffix_sum = [0] * (len(items) + 1)
        for index in range(len(items) - 1, -1, -1):
            suffix_sum[index] = (
                suffix_sum[index + 1] + items[index].length_mm + self.kerf_mm
            )

        def copy_bins(bins: list[_SearchBin]) -> list[_SearchBin]:
            return [
                _SearchBin(
                    bin_.stock,
                    bin_.remaining_mm,
                    list(bin_.cuts),
                    bin_.kerf_loss_mm,
                )
                for bin_ in bins
            ]

        def score_bins(bins: list[_SearchBin]) -> tuple[int, int, int, int, int]:
            return self._score_patterns(bins)

        def purchased_count(bins: list[_SearchBin]) -> int:
            used = [bin_ for bin_ in bins if bin_.cuts]
            return int(sum(bin_.stock.source == StockSource.NEW for bin_ in used))

        def search(index: int, bins: list[_SearchBin], purchased: int) -> None:
            nonlocal best_bins, best_score
            if index == len(items):
                candidate_score = score_bins(bins)
                if candidate_score < best_score:
                    best_score = candidate_score
                    best_bins = copy_bins(bins)
                return

            remaining_capacity = sum(bin_.remaining_mm for bin_ in bins)
            additional = max(0, suffix_sum[index] - remaining_capacity)
            lower_bound = purchased + ceil(additional / self.stock_length_mm)
            if lower_bound > best_score[0]:
                return

            item = items[index]
            required_mm = item.length_mm + self.kerf_mm
            candidates = [
                (bin_index, bin_)
                for bin_index, bin_ in enumerate(bins)
                if bin_.remaining_mm >= required_mm
            ]
            candidates.sort(
                key=lambda pair: (
                    pair[1].remaining_mm - required_mm,
                    pair[1].stock.source == StockSource.NEW,
                    pair[1].stock.id,
                )
            )

            seen_states: set[tuple[int, StockSource]] = set()
            for bin_index, bin_ in candidates:
                state = (bin_.remaining_mm, bin_.stock.source)
                if state in seen_states:
                    continue
                seen_states.add(state)
                bin_.remaining_mm -= required_mm
                bin_.cuts.append(item)
                bin_.kerf_loss_mm += self.kerf_mm
                search(index + 1, bins, purchased)
                bin_.kerf_loss_mm -= self.kerf_mm
                bin_.cuts.pop()
                bin_.remaining_mm += required_mm

            if purchased + 1 <= best_score[0]:
                new_index = purchased_count(bins) + 1
                stock = StockPiece(
                    id=f"NEW-{diameter}-E{new_index:05d}",
                    diameter_mm=diameter,
                    length_mm=self.stock_length_mm,
                    source=StockSource.NEW,
                )
                bins.append(
                    _SearchBin(
                        stock=stock,
                        remaining_mm=self.stock_length_mm - required_mm,
                        cuts=[item],
                        kerf_loss_mm=self.kerf_mm,
                    )
                )
                search(index + 1, bins, purchased + 1)
                bins.pop()

        search(0, initial_bins, 0)
        if best_bins is None:
            raise RuntimeError("solver failed to produce a feasible cutting plan")
        return [
            CutPattern(
                stock=bin_.stock,
                cuts=list(bin_.cuts),
                remaining_mm=bin_.remaining_mm,
                kerf_loss_mm=bin_.kerf_loss_mm,
            )
            for bin_ in best_bins
            if bin_.cuts
        ]

    def _score_patterns(self, bins: list[_SearchBin]) -> tuple[int, int, int, int, int]:
        return _score_bins(bins, self.min_reusable_mm)

    def _build_result(
        self,
        patterns: list[CutPattern],
        demands: list[CutDemand],
    ) -> OptimizationResult:
        purchased_length = sum(
            pattern.stock.length_mm
            for pattern in patterns
            if pattern.stock.source == StockSource.NEW
        )
        remnant_used = sum(
            pattern.used_mm
            for pattern in patterns
            if pattern.stock.source == StockSource.REMNANT
        )
        reusable_output = sum(
            pattern.remaining_mm
            for pattern in patterns
            if pattern.remaining_mm >= self.min_reusable_mm
        )
        scrap_output = sum(
            pattern.remaining_mm
            for pattern in patterns
            if pattern.remaining_mm < self.min_reusable_mm
        )
        return OptimizationResult(
            patterns=tuple(patterns),
            demand_length_mm=sum(d.length_mm * d.quantity for d in demands),
            purchased_length_mm=purchased_length,
            remnant_input_used_mm=remnant_used,
            reusable_output_mm=reusable_output,
            scrap_output_mm=scrap_output,
            kerf_loss_mm=sum(pattern.kerf_loss_mm for pattern in patterns),
        )


class CpSatCutOptimizer(BranchAndBoundCutOptimizer):
    """Scalable CP-SAT optimizer for realistic project-sized cutting lists."""

    def __init__(
        self,
        stock_length_mm: int = 12_000,
        min_reusable_mm: int = 1_000,
        kerf_mm: int = 0,
        max_items: int = 500,
        time_limit_seconds: float = 12.0,
    ) -> None:
        super().__init__(stock_length_mm, min_reusable_mm, kerf_mm, max_items)
        if time_limit_seconds <= 0:
            raise ValueError("time limit must be positive")
        self.time_limit_seconds = time_limit_seconds

    def optimize(
        self,
        demands: Iterable[CutDemand],
        remnants: Iterable[StockPiece] = (),
    ) -> OptimizationResult:
        demand_list = list(demands)
        remnant_list = list(remnants)
        item_count = sum(demand.quantity for demand in demand_list)
        if not demand_list:
            raise ValueError("at least one demand is required")
        if item_count > self.max_items:
            raise ValueError(
                f"advanced solver limit is {self.max_items} pieces; received {item_count}"
            )

        by_diameter: dict[int, list[CutItem]] = defaultdict(list)
        for demand in demand_list:
            if demand.length_mm + self.kerf_mm > self.stock_length_mm:
                raise ValueError(
                    f"{demand.mark}: required length exceeds standard stock length"
                )
            by_diameter[demand.diameter_mm].extend(
                CutItem(demand.mark, demand.length_mm, demand.phase)
                for _ in range(demand.quantity)
            )

        remnants_by_diameter: dict[int, list[StockPiece]] = defaultdict(list)
        for remnant in remnant_list:
            remnants_by_diameter[remnant.diameter_mm].append(remnant)

        patterns: list[CutPattern] = []
        for diameter in sorted(by_diameter):
            patterns.extend(
                self._solve_cpsat_diameter(
                    diameter,
                    by_diameter[diameter],
                    remnants_by_diameter[diameter],
                )
            )
        return self._build_result(patterns, demand_list)

    def _solve_cpsat_diameter(
        self,
        diameter: int,
        items: list[CutItem],
        remnants: list[StockPiece],
    ) -> list[CutPattern]:
        items = sorted(items, key=lambda item: (-item.length_mm, item.phase, item.mark))
        synthetic_demands = [
            CutDemand(f"CP-{index}", diameter, item.length_mm, 1, item.phase)
            for index, item in enumerate(items)
        ]
        greedy_result = GreedyCutOptimizer(
            self.stock_length_mm,
            self.min_reusable_mm,
            self.kerf_mm,
        ).optimize(synthetic_demands, remnants)
        max_new = max(1, greedy_result.purchased_bar_count)

        stocks = list(sorted(remnants, key=lambda item: (-item.length_mm, item.id)))
        existing_count = len(stocks)
        for index in range(max_new):
            stocks.append(
                StockPiece(
                    id=f"NEW-{diameter}-CP{index + 1:05d}",
                    diameter_mm=diameter,
                    length_mm=self.stock_length_mm,
                    source=StockSource.NEW,
                )
            )

        model = cp_model.CpModel()
        used = [model.new_bool_var(f"used_{bin_index}") for bin_index in range(len(stocks))]
        assignments: dict[tuple[int, int], cp_model.IntVar] = {}
        required_lengths = [item.length_mm + self.kerf_mm for item in items]

        for item_index, required in enumerate(required_lengths):
            allowed = []
            for bin_index, stock in enumerate(stocks):
                if required <= stock.length_mm:
                    variable = model.new_bool_var(f"x_{item_index}_{bin_index}")
                    assignments[(item_index, bin_index)] = variable
                    allowed.append(variable)
            if not allowed:
                raise ValueError("no stock piece can satisfy one of the demands")
            model.add_exactly_one(allowed)

        remaining_vars = []
        scrap_length_vars = []
        reusable_piece_vars = []
        reusable_length_vars = []
        for bin_index, stock in enumerate(stocks):
            assigned = [
                (required_lengths[item_index], assignments[(item_index, bin_index)])
                for item_index in range(len(items))
                if (item_index, bin_index) in assignments
            ]
            remaining = model.new_int_var(0, stock.length_mm, f"remaining_{bin_index}")
            scrap_length = model.new_int_var(0, stock.length_mm, f"scrap_{bin_index}")
            reusable_length = model.new_int_var(0, stock.length_mm, f"reusable_len_{bin_index}")
            scrap_piece = model.new_bool_var(f"scrap_piece_{bin_index}")
            reusable_piece = model.new_bool_var(f"reusable_piece_{bin_index}")
            if assigned:
                assigned_length = sum(length * variable for length, variable in assigned)
                model.add(
                    assigned_length <= stock.length_mm * used[bin_index]
                )
                model.add(sum(variable for _, variable in assigned) >= used[bin_index])
                model.add(remaining == stock.length_mm * used[bin_index] - assigned_length)
            else:
                model.add(used[bin_index] == 0)
                model.add(remaining == 0)

            if self.min_reusable_mm > 0:
                model.add(scrap_piece + reusable_piece == used[bin_index])
                model.add(remaining <= self.min_reusable_mm - 1).only_enforce_if(scrap_piece)
                model.add(remaining >= self.min_reusable_mm).only_enforce_if(reusable_piece)
            else:
                model.add(scrap_piece == 0)
                model.add(reusable_piece == used[bin_index])
            model.add(scrap_length == remaining).only_enforce_if(scrap_piece)
            model.add(scrap_length == 0).only_enforce_if(scrap_piece.Not())
            model.add(reusable_length == remaining).only_enforce_if(reusable_piece)
            model.add(reusable_length == 0).only_enforce_if(reusable_piece.Not())
            remaining_vars.append(remaining)
            scrap_length_vars.append(scrap_length)
            reusable_piece_vars.append(reusable_piece)
            reusable_length_vars.append(reusable_length)

        for bin_index in range(existing_count, len(stocks) - 1):
            model.add(used[bin_index] >= used[bin_index + 1])

        total_capacity = sum(stock.length_mm for stock in stocks)
        longest_reusable = model.new_int_var(0, total_capacity, "longest_reusable")
        model.add_max_equality(longest_reusable, reusable_length_vars)
        reusable_weight = total_capacity + 1
        waste_weight = (len(stocks) + 1) * reusable_weight
        scrap_weight = (total_capacity + 1) * waste_weight
        new_bar_weight = (total_capacity + 1) * scrap_weight
        new_bar_count = sum(used[index] for index in range(existing_count, len(stocks)))
        real_scrap = sum(scrap_length_vars)
        total_waste = sum(remaining_vars)
        reusable_piece_count = sum(reusable_piece_vars)
        model.minimize(
            new_bar_weight * new_bar_count
            + scrap_weight * real_scrap
            + waste_weight * total_waste
            + reusable_weight * reusable_piece_count
            - longest_reusable
        )

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self.time_limit_seconds
        solver.parameters.num_search_workers = 8
        solver.parameters.random_seed = 0
        status = solver.solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            raise RuntimeError("advanced solver could not find a feasible plan")

        patterns: list[CutPattern] = []
        for bin_index, stock in enumerate(stocks):
            if not solver.boolean_value(used[bin_index]):
                continue
            cuts = [
                items[item_index]
                for item_index in range(len(items))
                if (item_index, bin_index) in assignments
                and solver.boolean_value(assignments[(item_index, bin_index)])
            ]
            kerf_loss = self.kerf_mm * len(cuts)
            remaining = stock.length_mm - sum(item.length_mm for item in cuts) - kerf_loss
            patterns.append(
                CutPattern(
                    stock=stock,
                    cuts=cuts,
                    remaining_mm=remaining,
                    kerf_loss_mm=kerf_loss,
                )
            )
        return patterns
