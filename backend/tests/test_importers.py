import sys
import unittest
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rebarflow.importers import CsvDemandImporter, XlsxDemandImporter
from openpyxl import Workbook


class CsvDemandImporterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.importer = CsvDemandImporter()

    def test_imports_turkish_semicolon_csv(self) -> None:
        result = self.importer.import_text(
            "Poz;Çap;Boy;Adet;Faz\nK1;16;4200;4;1\nK2;12;2800;8;2\n"
        )
        self.assertEqual(result.accepted_count, 2)
        self.assertEqual(result.rejected_count, 0)
        self.assertEqual(result.demands[0].diameter_mm, 16)

    def test_rejects_bad_rows_without_losing_valid_rows(self) -> None:
        result = self.importer.import_text(
            "mark,diameter_mm,length_mm,quantity\nA,16,3000,2\nB,x,2500,1\n"
        )
        self.assertEqual(result.accepted_count, 1)
        self.assertEqual(result.rejected_count, 1)
        self.assertEqual(result.issues[0].row, 3)

    def test_reports_missing_columns(self) -> None:
        with self.assertRaisesRegex(ValueError, "Zorunlu kolonlar"):
            self.importer.import_text("Poz;Boy\nA;3000\n")

    def test_accepts_field_heading_variants(self) -> None:
        variants = [
            ("Çap", "Boy", "Adet"),
            ("Çap (mm)", "Boy (mm)", "Miktar"),
            ("Ø", "Uzunluk", "Quantity"),
            ("Ø mm", "Uzunluk (mm)", "Adet"),
            ("Fi", "Kesim Boyu", "Miktar"),
            ("Donatı Çapı", "Kesim Boyu (mm)", "Quantity"),
        ]
        for diameter_header, length_header, quantity_header in variants:
            with self.subTest(headers=(diameter_header, length_header, quantity_header)):
                result = self.importer.import_text(
                    f"Poz;{diameter_header};{length_header};{quantity_header}\n"
                    "K1;16;4200;2\n"
                )
                self.assertEqual(result.accepted_count, 1)
                self.assertEqual(result.demands[0].diameter_mm, 16)
                self.assertEqual(result.demands[0].length_mm, 4200)
                self.assertEqual(result.demands[0].quantity, 2)


if __name__ == "__main__":
    unittest.main()


class XlsxDemandImporterTests(unittest.TestCase):
    def test_imports_product_bbs_template(self) -> None:
        template = Path(__file__).resolve().parents[1] / "assets" / "RebarFlow-BBS-Sablonu.xlsx"
        result = XlsxDemandImporter().import_bytes(template.read_bytes())
        self.assertEqual(result.accepted_count, 4)
        self.assertEqual(result.rejected_count, 0)
        self.assertEqual(result.demands[0].mark, "K1-ALT")

    def test_imports_heading_variants_from_xlsx(self) -> None:
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Poz", "Donatı Çapı", "Kesim Boyu (mm)", "Miktar"])
        sheet.append(["K1", 16, 4200, 2])
        content = BytesIO()
        workbook.save(content)

        result = XlsxDemandImporter().import_bytes(content.getvalue())

        self.assertEqual(result.accepted_count, 1)
        self.assertEqual(result.demands[0].diameter_mm, 16)
        self.assertEqual(result.demands[0].length_mm, 4200)
        self.assertEqual(result.demands[0].quantity, 2)
