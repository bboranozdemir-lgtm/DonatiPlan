from __future__ import annotations

import csv
import io
import posixpath
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from xml.etree import ElementTree

from .models import CutDemand


@dataclass(frozen=True, slots=True)
class ImportIssue:
    row: int
    field: str
    message: str


@dataclass(frozen=True, slots=True)
class DemandImportResult:
    demands: tuple[CutDemand, ...]
    issues: tuple[ImportIssue, ...]

    @property
    def accepted_count(self) -> int:
        return len(self.demands)

    @property
    def rejected_count(self) -> int:
        return len({issue.row for issue in self.issues})


class CsvDemandImporter:
    """Imports common Turkish/English BBS column names from CSV text."""

    REQUIRED_COLUMNS_MESSAGE = (
        "Zorunlu kolonlar bulunamadı. CSV/XLSX başlıklarını kontrol edin: "
        "Poz, Çap/Çap (mm)/Ø/Fi/Donatı Çapı, Boy/Uzunluk/Kesim Boyu ve Adet/Miktar/Quantity."
    )

    ALIASES = {
        "mark": {"poz", "mark", "bar_mark", "parca", "parca_no"},
        "diameter_mm": {
            "cap",
            "cap_mm",
            "diameter",
            "diameter_mm",
            "donati_capi",
            "donati_capi_mm",
            "fi",
            "fi_mm",
        },
        "length_mm": {
            "boy",
            "boy_mm",
            "uzunluk",
            "uzunluk_mm",
            "length",
            "length_mm",
            "kesim_boyu",
            "kesim_boyu_mm",
        },
        "quantity": {"adet", "quantity", "qty", "miktar"},
        "phase": {"faz", "phase", "imalat_fazi"},
    }

    def import_text(self, content: str) -> DemandImportResult:
        if not content.strip():
            raise ValueError("CSV content cannot be empty")

        sample = content[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel

        reader = csv.DictReader(io.StringIO(content), dialect=dialect)
        if not reader.fieldnames:
            raise ValueError("CSV header row is missing")

        return self._import_dict_rows(reader.fieldnames, list(reader), start_row=2)

    def _import_dict_rows(
        self,
        fieldnames: list[str],
        rows: list[dict[str, str | None]],
        *,
        start_row: int,
    ) -> DemandImportResult:
        columns = self._map_columns(fieldnames)

        missing = [field for field in ("mark", "diameter_mm", "length_mm", "quantity") if field not in columns]
        if missing:
            raise ValueError(self.REQUIRED_COLUMNS_MESSAGE)

        demands: list[CutDemand] = []
        issues: list[ImportIssue] = []
        for row_number, row in enumerate(rows, start=start_row):
            if not any((value or "").strip() for value in row.values()):
                continue
            row_issues: list[ImportIssue] = []
            values: dict[str, str] = {}
            for target, source in columns.items():
                values[target] = (row.get(source) or "").strip()

            mark = values.get("mark", "")
            if not mark:
                row_issues.append(ImportIssue(row_number, "mark", "Poz boş bırakılamaz."))

            parsed: dict[str, int] = {}
            for field in ("diameter_mm", "length_mm", "quantity"):
                try:
                    parsed[field] = self._positive_int(values.get(field, ""))
                except ValueError:
                    row_issues.append(
                        ImportIssue(row_number, field, "Pozitif tam sayı bekleniyor.")
                    )

            phase_text = values.get("phase", "0") or "0"
            try:
                phase = self._nonnegative_int(phase_text)
            except ValueError:
                phase = 0
                row_issues.append(
                    ImportIssue(row_number, "phase", "Sıfır veya pozitif tam sayı bekleniyor.")
                )

            if row_issues:
                issues.extend(row_issues)
                continue

            demands.append(
                CutDemand(
                    mark=mark,
                    diameter_mm=parsed["diameter_mm"],
                    length_mm=parsed["length_mm"],
                    quantity=parsed["quantity"],
                    phase=phase,
                )
            )

        return DemandImportResult(tuple(demands), tuple(issues))

    def _map_columns(self, headers: list[str]) -> dict[str, str]:
        normalized = {self._normalize(header): header for header in headers}
        result: dict[str, str] = {}
        for target, aliases in self.ALIASES.items():
            for alias in aliases:
                if alias in normalized:
                    result[target] = normalized[alias]
                    break
        return result

    @staticmethod
    def _positive_int(value: str) -> int:
        parsed = float(value.replace(",", "."))
        if not parsed.is_integer() or parsed <= 0:
            raise ValueError
        return int(parsed)

    @staticmethod
    def _nonnegative_int(value: str) -> int:
        parsed = float(value.replace(",", "."))
        if not parsed.is_integer() or parsed < 0:
            raise ValueError
        return int(parsed)

    @staticmethod
    def _normalize(value: str) -> str:
        value = CsvDemandImporter._repair_mojibake(value)
        value = value.lstrip("\ufeff").strip().casefold()
        value = (
            value.replace("ı", "i")
            .replace("İ", "i")
            .replace("ø", "cap")
            .replace("Ø", "cap")
            .replace("ϕ", "fi")
            .replace("φ", "fi")
        )
        value = "".join(
            character
            for character in unicodedata.normalize("NFKD", value)
            if not unicodedata.combining(character)
        )
        value = re.sub(r"[^a-z0-9]+", "_", value, flags=re.IGNORECASE)
        return value.strip("_")

    @staticmethod
    def _repair_mojibake(value: str) -> str:
        if not any(marker in value for marker in ("Ã", "Ä", "Å")):
            return value
        try:
            return value.encode("latin1").decode("utf-8")
        except UnicodeError:
            return value


class XlsxDemandImporter(CsvDemandImporter):
    """Reads the first useful worksheet from an XLSX without executing macros."""

    MAX_UNCOMPRESSED_BYTES = 50_000_000
    MAX_ZIP_ENTRIES = 10_000

    def import_bytes(self, content: bytes) -> DemandImportResult:
        if not content:
            raise ValueError("XLSX content cannot be empty")
        rows = self._read_first_sheet(content)
        if not rows:
            raise ValueError("XLSX worksheet is empty")

        best_index = -1
        best_score = -1
        for index, row in enumerate(rows[:30]):
            headers = [str(value) for value in row]
            mapped = self._map_columns(headers)
            score = sum(
                field in mapped
                for field in ("mark", "diameter_mm", "length_mm", "quantity", "phase")
            )
            if score >= best_score:
                best_index = index
                best_score = score

        if best_index < 0 or best_score < 4:
            raise ValueError(self.REQUIRED_COLUMNS_MESSAGE)

        headers = [str(value) for value in rows[best_index]]
        records: list[dict[str, str | None]] = []
        for values in rows[best_index + 1 :]:
            record = {
                header: str(values[index]).strip() if index < len(values) else ""
                for index, header in enumerate(headers)
            }
            records.append(record)
        return self._import_dict_rows(
            headers,
            records,
            start_row=best_index + 2,
        )

    def _read_first_sheet(self, content: bytes) -> list[list[str]]:
        try:
            archive = zipfile.ZipFile(io.BytesIO(content))
        except zipfile.BadZipFile as exc:
            raise ValueError("file is not a valid XLSX archive") from exc

        with archive:
            infos = archive.infolist()
            if len(infos) > self.MAX_ZIP_ENTRIES:
                raise ValueError("XLSX contains too many files")
            if sum(info.file_size for info in infos) > self.MAX_UNCOMPRESSED_BYTES:
                raise ValueError("XLSX uncompressed content is too large")

            names = set(archive.namelist())
            required = {"xl/workbook.xml", "xl/_rels/workbook.xml.rels"}
            if not required.issubset(names):
                raise ValueError("XLSX workbook metadata is missing")

            workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
            relationships = ElementTree.fromstring(
                archive.read("xl/_rels/workbook.xml.rels")
            )
            relation_targets = {
                relation.attrib["Id"]: relation.attrib["Target"]
                for relation in relationships
            }
            relation_namespace = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
            sheets = workbook.findall(
                ".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheet"
            )
            if not sheets:
                raise ValueError("XLSX contains no worksheets")
            relation_id = sheets[0].attrib[relation_namespace]
            target = relation_targets.get(relation_id)
            if not target:
                raise ValueError("XLSX worksheet relationship is missing")
            sheet_path = self._normalize_sheet_path(target)
            if sheet_path not in names:
                raise ValueError("XLSX worksheet data is missing")

            shared_strings: list[str] = []
            if "xl/sharedStrings.xml" in names:
                shared_root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
                shared_strings = [
                    "".join(node.text or "" for node in item.iter() if node.tag.endswith("}t"))
                    for item in shared_root
                ]

            sheet_root = ElementTree.fromstring(archive.read(sheet_path))
            namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
            result: list[list[str]] = []
            for row in sheet_root.findall(f".//{namespace}row"):
                values: dict[int, str] = {}
                for cell in row.findall(f"{namespace}c"):
                    reference = cell.attrib.get("r", "A1")
                    column = self._column_index(reference)
                    cell_type = cell.attrib.get("t", "n")
                    value_node = cell.find(f"{namespace}v")
                    value = value_node.text if value_node is not None else ""
                    if cell_type == "s" and value:
                        value = shared_strings[int(value)]
                    elif cell_type == "inlineStr":
                        value = "".join(
                            node.text or "" for node in cell.iter() if node.tag.endswith("}t")
                        )
                    values[column] = value or ""
                if values:
                    width = max(values) + 1
                    result.append([values.get(index, "") for index in range(width)])
                else:
                    result.append([])
            return result

    @staticmethod
    def _normalize_sheet_path(target: str) -> str:
        if target.startswith("/"):
            return target.lstrip("/")
        return posixpath.normpath(posixpath.join("xl", target))

    @staticmethod
    def _column_index(reference: str) -> int:
        letters = "".join(character for character in reference if character.isalpha())
        index = 0
        for character in letters.upper():
            index = index * 26 + (ord(character) - ord("A") + 1)
        return max(0, index - 1)
