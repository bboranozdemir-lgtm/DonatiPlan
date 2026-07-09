import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rebarflow.store import SqliteStore


class SqliteStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.store = SqliteStore(Path(self.tempdir.name) / "test.db")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_project_and_inventory_survive_new_store_instance(self) -> None:
        project = self.store.create_project("Konut A", "Ankara")
        self.store.replace_available_remnants(
            project.id,
            [
                {
                    "stock_code": "ART-01",
                    "diameter_mm": 16,
                    "length_mm": 3400,
                    "steel_grade": "B420C",
                }
            ],
        )

        reopened = SqliteStore(self.store.path)
        self.assertEqual(reopened.get_project(project.id).name, "Konut A")
        self.assertEqual(reopened.list_remnants(project.id)[0].stock_code, "ART-01")

    def test_project_settings_are_persistent_and_validated(self) -> None:
        project = self.store.create_project("Ayar Testi")
        defaults = self.store.get_project_settings(project.id)
        self.assertEqual(defaults.stock_length_mm, 12000)

        updated = self.store.update_project_settings(
            project.id,
            stock_length_mm=14000,
            min_reusable_mm=1200,
            kerf_mm=4,
            steel_price_per_kg=31.5,
            carbon_kg_per_kg=1.8,
            currency="try",
        )
        self.assertEqual(updated.stock_length_mm, 14000)
        self.assertEqual(updated.currency, "TRY")
        self.assertEqual(SqliteStore(self.store.path).get_project_settings(project.id).kerf_mm, 4)

        with self.assertRaisesRegex(ValueError, "cannot exceed"):
            self.store.update_project_settings(
                project.id,
                stock_length_mm=1000,
                min_reusable_mm=1200,
                kerf_mm=0,
                steel_price_per_kg=0,
                carbon_kg_per_kg=0,
                currency="TRY",
            )

    def test_project_demand_draft_is_persistent_and_ordered(self) -> None:
        project = self.store.create_project("BBS Taslağı")
        saved = self.store.replace_project_demands(
            project.id,
            [
                {"mark": "K2", "diameter_mm": 12, "length_mm": 2800, "quantity": 8, "phase": 2},
                {"mark": "K1", "diameter_mm": 16, "length_mm": 4200, "quantity": 4, "phase": 1},
            ],
        )
        self.assertEqual([item.mark for item in saved], ["K2", "K1"])
        reopened = SqliteStore(self.store.path)
        self.assertEqual(reopened.list_project_demands(project.id)[1].quantity, 4)

    def test_replaces_only_available_inventory(self) -> None:
        project = self.store.create_project("Konut B")
        self.store.replace_available_remnants(
            project.id,
            [{"stock_code": "OLD", "diameter_mm": 12, "length_mm": 2000}],
        )
        rows = self.store.replace_available_remnants(
            project.id,
            [{"stock_code": "NEW", "diameter_mm": 14, "length_mm": 2500}],
        )
        self.assertEqual([row.stock_code for row in rows], ["NEW"])

    def test_inventory_sync_preserves_identity_and_audits_only_changes(self) -> None:
        project = self.store.create_project("Kimlik Testi")
        original = self.store.replace_available_remnants(
            project.id,
            [{"stock_code": "QR-SABIT", "diameter_mm": 16, "length_mm": 3000}],
        )[0]
        movement_count = len(self.store.list_movements(project.id))

        unchanged = self.store.replace_available_remnants(
            project.id,
            [{"stock_code": "QR-SABIT", "diameter_mm": 16, "length_mm": 3000}],
        )[0]
        self.assertEqual(unchanged.id, original.id)
        self.assertEqual(len(self.store.list_movements(project.id)), movement_count)

        updated = self.store.replace_available_remnants(
            project.id,
            [{"stock_code": "QR-SABIT", "diameter_mm": 16, "length_mm": 2750}],
        )[0]
        self.assertEqual(updated.id, original.id)
        self.assertEqual(updated.length_mm, 2750)
        self.assertEqual(
            self.store.list_movements(project.id)[0].movement_type,
            "inventory_updated",
        )

    def test_inventory_sync_rejects_historical_code_reuse(self) -> None:
        project = self.store.create_project("Kod Testi")
        item = self.store.replace_available_remnants(
            project.id,
            [{"stock_code": "AYNI-KOD", "diameter_mm": 12, "length_mm": 2200}],
        )[0]
        self.store.transition_remnant(project.id, item.id, "reserved")
        with self.assertRaisesRegex(ValueError, "historical"):
            self.store.replace_available_remnants(
                project.id,
                [{"stock_code": "ayni-kod", "diameter_mm": 12, "length_mm": 2200}],
            )

    def test_saves_optimization_history(self) -> None:
        project = self.store.create_project("Konut C")
        run = self.store.save_run(
            project.id,
            requested_mode="auto",
            solver_used="exact",
            piece_count=3,
            purchased_bar_count=1,
            purchase_waste_rate=0.0,
            request_data={"demands": []},
            result_data={"patterns": []},
        )
        self.assertEqual(run.status, "draft")
        self.assertEqual(self.store.list_runs(project.id)[0].id, run.id)

    def test_rejects_duplicate_stock_codes(self) -> None:
        project = self.store.create_project("Konut D")
        with self.assertRaisesRegex(ValueError, "unique"):
            self.store.replace_available_remnants(
                project.id,
                [
                    {"stock_code": "A", "diameter_mm": 12, "length_mm": 1000},
                    {"stock_code": "A", "diameter_mm": 12, "length_mm": 2000},
                ],
            )

    def test_project_backup_round_trip(self) -> None:
        project = self.store.create_project("Yedek Testi", "Bursa")
        self.store.replace_project_demands(
            project.id,
            [{"mark": "P1", "diameter_mm": 14, "length_mm": 3300, "quantity": 5, "phase": 1}],
        )
        self.store.replace_available_remnants(
            project.id,
            [{"stock_code": "YDK-01", "diameter_mm": 20, "length_mm": 4100}],
        )
        backup = self.store.export_project(project.id)
        restored = self.store.restore_project(backup)
        self.assertNotEqual(restored.id, project.id)
        self.assertIn("Geri Yüklendi", restored.name)
        self.assertEqual(self.store.list_remnants(restored.id)[0].stock_code, "YDK-01")
        self.assertEqual(self.store.list_project_demands(restored.id)[0].mark, "P1")

    def test_users_passwords_and_sessions(self) -> None:
        admin = self.store.bootstrap_admin("yonetici", "guclu-parola-123")
        self.assertEqual(admin.role, "admin")
        self.assertIsNone(self.store.authenticate_user("yonetici", "yanlis-parola"))
        authenticated = self.store.authenticate_user("YONETICI", "guclu-parola-123")
        self.assertEqual(authenticated.id, admin.id)
        token = self.store.create_session(admin.id)
        self.assertEqual(self.store.user_for_session(token).username, "yonetici")
        self.store.delete_session(token)
        self.assertIsNone(self.store.user_for_session(token))

    def test_manual_inventory_transitions_are_audited(self) -> None:
        project = self.store.create_project("QR Testi")
        item = self.store.replace_available_remnants(
            project.id,
            [{"stock_code": "QR-01", "diameter_mm": 16, "length_mm": 2800}],
        )[0]
        reserved = self.store.transition_remnant(
            project.id, item.id, "reserved", "Kolon K1 için"
        )
        self.assertEqual(reserved.status, "reserved")
        consumed = self.store.transition_remnant(project.id, item.id, "consumed")
        self.assertEqual(consumed.status, "consumed")
        movement_types = [m.movement_type for m in self.store.list_movements(project.id)]
        self.assertIn("manual_reserved", movement_types)
        self.assertIn("manual_consumed", movement_types)
        with self.assertRaisesRegex(ValueError, "not allowed"):
            self.store.transition_remnant(project.id, item.id, "available")

    def test_commit_consumes_input_and_creates_output_remnant(self) -> None:
        project = self.store.create_project("Konut E")
        self.store.replace_available_remnants(
            project.id,
            [{"stock_code": "ART-01", "diameter_mm": 16, "length_mm": 5000}],
        )
        run = self.store.save_run(
            project.id,
            requested_mode="auto",
            solver_used="exact",
            piece_count=1,
            purchased_bar_count=0,
            purchase_waste_rate=0.0,
            request_data={},
            result_data={
                "patterns": [
                    {
                        "stock_id": "ART-01",
                        "diameter_mm": 16,
                        "stock_length_mm": 5000,
                        "source": "remnant",
                        "remaining_mm": 2000,
                    }
                ]
            },
        )
        committed = self.store.commit_run(project.id, run.id)
        self.assertEqual(committed.consumed_remnant_count, 1)
        self.assertEqual(committed.available_output_count, 1)
        available = self.store.list_remnants(project.id)
        self.assertEqual(len(available), 1)
        self.assertEqual(available[0].length_mm, 2000)
        self.assertEqual(self.store.get_run(project.id, run.id).status, "committed")
        movement_types = {item.movement_type for item in self.store.list_movements(project.id)}
        self.assertIn("inventory_added", movement_types)
        self.assertIn("consumed", movement_types)
        self.assertIn("output_available", movement_types)

        with self.assertRaisesRegex(ValueError, "already committed"):
            self.store.commit_run(project.id, run.id)


if __name__ == "__main__":
    unittest.main()
