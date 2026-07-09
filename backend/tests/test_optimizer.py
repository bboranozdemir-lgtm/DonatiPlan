import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rebarflow.models import CutDemand, StockPiece, StockSource
from rebarflow.optimizer import BranchAndBoundCutOptimizer, CpSatCutOptimizer, GreedyCutOptimizer
from rebarflow.service import OptimizationMode, OptimizationService


class GreedyCutOptimizerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.optimizer = GreedyCutOptimizer(stock_length_mm=12_000, min_reusable_mm=1_000)

    def test_packs_compatible_lengths_into_one_bar(self) -> None:
        result = self.optimizer.optimize(
            [
                CutDemand("K1", 16, 4_200, 2),
                CutDemand("K2", 16, 3_600, 1),
            ]
        )
        self.assertEqual(result.purchased_bar_count, 1)
        self.assertEqual(result.patterns[0].remaining_mm, 0)
        self.assertEqual(result.purchase_waste_rate, 0.0)

    def test_never_mixes_diameters(self) -> None:
        result = self.optimizer.optimize(
            [
                CutDemand("A", 12, 6_000, 1),
                CutDemand("B", 16, 6_000, 1),
            ]
        )
        self.assertEqual(result.purchased_bar_count, 2)
        for pattern in result.patterns:
            self.assertTrue(all(pattern.stock.diameter_mm in (12, 16) for _ in pattern.cuts))

    def test_prefers_existing_remnant(self) -> None:
        result = self.optimizer.optimize(
            [CutDemand("D1", 14, 3_000, 1)],
            [StockPiece("R-001", 14, 3_400, StockSource.REMNANT)],
        )
        self.assertEqual(result.purchased_bar_count, 0)
        self.assertEqual(result.remnant_input_used_mm, 3_000)
        self.assertEqual(result.scrap_output_mm, 400)

    def test_existing_remnant_only_rates_use_used_source_not_new_stock(self) -> None:
        result = self.optimizer.optimize(
            [CutDemand("D1", 16, 3_000, 1)],
            [StockPiece("R-016-3500", 16, 3_500, StockSource.REMNANT)],
        )

        self.assertEqual(result.purchased_length_mm, 0)
        self.assertEqual(result.purchased_bar_count, 0)
        self.assertEqual(result.remnant_input_used_mm, 3_000)
        self.assertEqual(result.remnant_source_used_mm, 3_500)
        self.assertEqual(result.used_source_length_mm, 3_500)
        self.assertEqual(result.total_waste_mm, 500)
        self.assertEqual(result.real_scrap_mm, 500)
        self.assertEqual(result.new_stock_waste_mm, 0)
        self.assertEqual(result.new_stock_waste_rate, 0)
        self.assertAlmostEqual(result.waste_rate, 500 / 3_500)
        self.assertAlmostEqual(result.real_scrap_rate, 500 / 3_500)

    def test_rejects_impossible_length(self) -> None:
        with self.assertRaisesRegex(ValueError, "exceeds"):
            self.optimizer.optimize([CutDemand("X", 16, 12_500, 1)])

    def test_rejects_negative_empty_or_invalid_demand_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "mark"):
            CutDemand("", 16, 1_000, 1)
        with self.assertRaisesRegex(ValueError, "positive"):
            CutDemand("NEG", 16, -1_000, 1)
        with self.assertRaisesRegex(ValueError, "positive"):
            CutDemand("ZERO", 16, 0, 1)
        with self.assertRaisesRegex(ValueError, "positive"):
            CutDemand("BADQ", 16, 1_000, 0)

    def test_result_conserves_length(self) -> None:
        result = self.optimizer.optimize(
            [CutDemand("A", 16, 4_000, 4)],
            [StockPiece("R-01", 16, 5_000)],
        )
        input_length = result.purchased_length_mm + 5_000
        output_length = (
            result.demand_length_mm + result.reusable_output_mm + result.scrap_output_mm
        )
        self.assertEqual(input_length, output_length)

    def test_accounts_for_cutting_kerf(self) -> None:
        optimizer = GreedyCutOptimizer(
            stock_length_mm=100,
            min_reusable_mm=10,
            kerf_mm=2,
        )
        result = optimizer.optimize([CutDemand("A", 16, 48, 2)])
        self.assertEqual(result.purchased_bar_count, 1)
        self.assertEqual(result.kerf_loss_mm, 4)
        self.assertEqual(
            result.purchased_length_mm,
            result.demand_length_mm + result.kerf_loss_mm + result.scrap_output_mm,
        )

    def test_multistart_prefers_less_real_scrap_with_same_bar_count(self) -> None:
        result = self.optimizer.optimize(
            [
                CutDemand("S1000", 16, 1_000, 4),
                CutDemand("L8500", 16, 8_500, 1),
            ]
        )
        remainders = sorted(pattern.remaining_mm for pattern in result.patterns)
        self.assertEqual(result.purchased_bar_count, 2)
        self.assertEqual(result.total_waste_mm, 11_500)
        self.assertEqual(result.real_scrap_mm, 0)
        self.assertEqual(remainders, [3_500, 8_000])

    def test_multistart_prefers_single_long_reusable_remnant(self) -> None:
        result = self.optimizer.optimize(
            [
                CutDemand("L6000", 16, 6_000, 2),
                CutDemand("L3000", 16, 3_000, 2),
            ]
        )
        reusable = sorted(
            pattern.remaining_mm
            for pattern in result.patterns
            if pattern.remaining_mm >= 1_000
        )
        self.assertEqual(result.purchased_bar_count, 2)
        self.assertEqual(result.real_scrap_mm, 0)
        self.assertEqual(reusable, [6_000])


class BranchAndBoundCutOptimizerTests(unittest.TestCase):
    def test_multistart_fast_matches_exact_on_known_counterexample(self) -> None:
        demands = [
            CutDemand(str(index), 16, length, 1)
            for index, length in enumerate((20, 20, 20, 25, 45, 60))
        ]
        greedy = GreedyCutOptimizer(stock_length_mm=100, min_reusable_mm=10)
        exact = BranchAndBoundCutOptimizer(
            stock_length_mm=100,
            min_reusable_mm=10,
            max_items=10,
        )
        self.assertEqual(greedy.optimize(demands).purchased_bar_count, 2)
        self.assertEqual(exact.optimize(demands).purchased_bar_count, 2)

    def test_exact_solver_finds_feasible_plan_and_conserves_material(self) -> None:
        optimizer = BranchAndBoundCutOptimizer(max_items=12)
        demands = [
            CutDemand("A", 16, 6_100, 2),
            CutDemand("B", 16, 5_900, 2),
            CutDemand("C", 16, 2_000, 2),
        ]
        result = optimizer.optimize(demands)
        self.assertEqual(result.purchased_bar_count, 3)
        self.assertEqual(
            result.purchased_length_mm,
            result.demand_length_mm + result.reusable_output_mm + result.scrap_output_mm,
        )

    def test_exact_solver_respects_piece_limit(self) -> None:
        optimizer = BranchAndBoundCutOptimizer(max_items=2)
        with self.assertRaisesRegex(ValueError, "limit"):
            optimizer.optimize([CutDemand("A", 12, 1_000, 3)])

    def test_total_waste_and_real_scrap_metrics_follow_reusable_threshold(self) -> None:
        demands = [
            CutDemand("A12-300", 12, 3_000, 2, 1),
            CutDemand("A12-450", 12, 4_500, 2, 1),
            CutDemand("A12-600", 12, 6_000, 1, 1),
            CutDemand("B16-400", 16, 4_000, 3, 2),
            CutDemand("B16-550", 16, 5_500, 2, 2),
            CutDemand("B16-250", 16, 2_500, 4, 2),
        ]

        result_1000 = BranchAndBoundCutOptimizer(min_reusable_mm=1_000, max_items=20).optimize(demands)
        self.assertEqual(result_1000.demand_length_mm, 54_000)
        self.assertEqual(result_1000.purchased_length_mm, 60_000)
        self.assertEqual(result_1000.purchased_bar_count, 5)
        self.assertEqual(result_1000.total_waste_mm, 6_000)
        self.assertAlmostEqual(result_1000.waste_rate, 0.10)
        self.assertEqual(result_1000.real_scrap_mm, 0)
        self.assertEqual(result_1000.real_scrap_rate, 0)
        self.assertEqual(result_1000.reusable_output_mm, 6_000)

        result_2000 = BranchAndBoundCutOptimizer(min_reusable_mm=2_000, max_items=20).optimize(demands)
        self.assertEqual(result_2000.total_waste_mm, 6_000)
        self.assertEqual(result_2000.real_scrap_mm, 0)
        self.assertEqual(result_2000.real_scrap_rate, 0)
        self.assertEqual(result_2000.reusable_output_mm, 6_000)

        result_500 = BranchAndBoundCutOptimizer(min_reusable_mm=500, max_items=20).optimize(demands)
        self.assertEqual(result_500.real_scrap_mm, 0)
        self.assertEqual(result_500.reusable_output_mm, 6_000)

        threshold_case = [CutDemand("TH-11000", 12, 11_000, 1)]
        self.assertEqual(
            BranchAndBoundCutOptimizer(min_reusable_mm=500).optimize(threshold_case).reusable_output_mm,
            1_000,
        )
        self.assertEqual(
            BranchAndBoundCutOptimizer(min_reusable_mm=1_000).optimize(threshold_case).reusable_output_mm,
            1_000,
        )
        result_threshold_2000 = BranchAndBoundCutOptimizer(min_reusable_mm=2_000).optimize(threshold_case)
        self.assertEqual(result_threshold_2000.real_scrap_mm, 1_000)
        self.assertEqual(result_threshold_2000.reusable_output_mm, 0)

    def test_prefers_one_long_reusable_remnant_over_two_shorter_same_diameter_remnants(self) -> None:
        result = BranchAndBoundCutOptimizer(min_reusable_mm=1_000, max_items=10).optimize(
            [
                CutDemand("L6000", 16, 6_000, 2),
                CutDemand("L3000", 16, 3_000, 2),
            ]
        )
        remainders = sorted(
            pattern.remaining_mm
            for pattern in result.patterns
            if pattern.remaining_mm >= 1_000
        )
        self.assertEqual(result.purchased_bar_count, 2)
        self.assertEqual(result.total_waste_mm, 6_000)
        self.assertEqual(remainders, [6_000])

    def test_reusable_remnants_from_different_diameters_are_not_merged(self) -> None:
        result = BranchAndBoundCutOptimizer(min_reusable_mm=1_000, max_items=10).optimize(
            [
                CutDemand("D12", 12, 6_000, 1),
                CutDemand("D16", 16, 6_000, 1),
            ]
        )
        reusable_by_diameter = sorted(
            (pattern.stock.diameter_mm, pattern.remaining_mm)
            for pattern in result.patterns
            if pattern.remaining_mm >= 1_000
        )
        self.assertEqual(result.purchased_bar_count, 2)
        self.assertEqual(result.reusable_output_mm, 12_000)
        self.assertEqual(reusable_by_diameter, [(12, 6_000), (16, 6_000)])

    def test_total_waste_rate_is_stable_when_demand_and_stock_totals_are_same(self) -> None:
        first = BranchAndBoundCutOptimizer(min_reusable_mm=1_000, max_items=10).optimize(
            [
                CutDemand("A", 16, 6_000, 2),
                CutDemand("B", 16, 3_000, 2),
            ]
        )
        second = BranchAndBoundCutOptimizer(min_reusable_mm=1_000, max_items=10).optimize(
            [
                CutDemand("C", 16, 5_000, 2),
                CutDemand("D", 16, 4_000, 2),
            ]
        )
        self.assertEqual(first.demand_length_mm, second.demand_length_mm)
        self.assertEqual(first.purchased_bar_count, second.purchased_bar_count)
        self.assertEqual(first.purchased_length_mm, second.purchased_length_mm)
        self.assertEqual(first.total_waste_mm, second.total_waste_mm)
        self.assertEqual(first.waste_rate, second.waste_rate)


class OptimizationServiceTests(unittest.TestCase):
    def test_auto_selects_exact_for_small_jobs(self) -> None:
        run = OptimizationService(exact_item_limit=5).run(
            [CutDemand("A", 12, 2_000, 2)]
        )
        self.assertEqual(run.solver_used, OptimizationMode.EXACT)

    def test_auto_selects_advanced_for_large_jobs(self) -> None:
        run = OptimizationService(exact_item_limit=2).run(
            [CutDemand("A", 12, 2_000, 3)]
        )
        self.assertEqual(run.solver_used, OptimizationMode.ADVANCED)

    def test_all_modes_enforce_total_piece_safety_limit(self) -> None:
        with self.assertRaisesRegex(ValueError, "500 pieces"):
            OptimizationService().run(
                [CutDemand("A", 12, 1000, 501)],
                mode=OptimizationMode.FAST,
            )

    def test_fast_mode_handles_large_data_quickly(self) -> None:
        demands = [
            CutDemand("D12-2400", 12, 2_400, 160),
            CutDemand("D16-3600", 16, 3_600, 160),
            CutDemand("D20-5100", 20, 5_100, 120),
        ]
        started = time.perf_counter()
        run = OptimizationService().run(demands, mode=OptimizationMode.FAST)
        elapsed = time.perf_counter() - started
        self.assertEqual(run.piece_count, 440)
        self.assertLess(elapsed, 2.0)
        self.assertGreater(run.result.purchased_bar_count, 0)


class CpSatCutOptimizerTests(unittest.TestCase):
    def test_advanced_solver_is_no_worse_than_greedy(self) -> None:
        demands = [
            CutDemand("A", 16, 4200, 20),
            CutDemand("B", 16, 3600, 20),
            CutDemand("C", 16, 1800, 20),
        ]
        greedy = GreedyCutOptimizer().optimize(demands)
        advanced = CpSatCutOptimizer(time_limit_seconds=5).optimize(demands)
        self.assertLessEqual(advanced.purchased_bar_count, greedy.purchased_bar_count)
        self.assertEqual(
            sum(len(pattern.cuts) for pattern in advanced.patterns),
            60,
        )


if __name__ == "__main__":
    unittest.main()
