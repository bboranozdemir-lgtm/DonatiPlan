from __future__ import annotations

import json
import base64
import hashlib
import hmac
import os
import secrets
import sqlite3
from collections.abc import Iterable
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class ProjectRecord:
    id: str
    name: str
    site: str
    description: str
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class ProjectSettingsRecord:
    project_id: str
    stock_length_mm: int
    min_reusable_mm: int
    kerf_mm: int
    steel_price_per_kg: float
    carbon_kg_per_kg: float
    currency: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class ProjectDemandRecord:
    id: str
    project_id: str
    mark: str
    diameter_mm: int
    length_mm: int
    quantity: int
    phase: int
    position: int


@dataclass(frozen=True, slots=True)
class RemnantRecord:
    id: str
    project_id: str
    stock_code: str
    diameter_mm: int
    length_mm: int
    steel_grade: str
    status: str
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class InventoryMovementRecord:
    id: str
    project_id: str
    stock_code: str
    movement_type: str
    diameter_mm: int
    length_mm: int
    run_id: str | None
    details: dict[str, Any]
    created_at: str


@dataclass(frozen=True, slots=True)
class UserRecord:
    id: str
    username: str
    role: str
    active: bool
    created_at: str


@dataclass(frozen=True, slots=True)
class OptimizationRunRecord:
    id: str
    project_id: str
    requested_mode: str
    solver_used: str
    status: str
    piece_count: int
    purchased_bar_count: int
    purchase_waste_rate: float
    request_data: dict[str, Any]
    result_data: dict[str, Any]
    created_at: str


@dataclass(frozen=True, slots=True)
class CommitResult:
    run_id: str
    consumed_remnant_count: int
    available_output_count: int
    scrap_output_count: int


class SqliteStore:
    """Small, explicit persistence layer for the local-first product."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def connection(self) -> Iterable[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self.connection() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;

                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    site TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS remnants (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    stock_code TEXT NOT NULL,
                    diameter_mm INTEGER NOT NULL CHECK (diameter_mm > 0),
                    length_mm INTEGER NOT NULL CHECK (length_mm > 0),
                    steel_grade TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('available', 'reserved', 'consumed', 'scrap')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(project_id, stock_code)
                );

                CREATE INDEX IF NOT EXISTS idx_remnants_project_status
                    ON remnants(project_id, status);

                CREATE TABLE IF NOT EXISTS optimization_runs (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    requested_mode TEXT NOT NULL,
                    solver_used TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('draft', 'committed')),
                    piece_count INTEGER NOT NULL,
                    purchased_bar_count INTEGER NOT NULL,
                    purchase_waste_rate REAL NOT NULL,
                    request_json TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_runs_project_created
                    ON optimization_runs(project_id, created_at DESC);
                """
            )
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version < 2:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS project_settings (
                        project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
                        stock_length_mm INTEGER NOT NULL CHECK (stock_length_mm > 0),
                        min_reusable_mm INTEGER NOT NULL CHECK (min_reusable_mm >= 0),
                        kerf_mm INTEGER NOT NULL CHECK (kerf_mm >= 0),
                        steel_price_per_kg REAL NOT NULL CHECK (steel_price_per_kg >= 0),
                        carbon_kg_per_kg REAL NOT NULL CHECK (carbon_kg_per_kg >= 0),
                        currency TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    """
                )
                now = self._now()
                connection.execute(
                    """
                    INSERT OR IGNORE INTO project_settings(
                        project_id, stock_length_mm, min_reusable_mm, kerf_mm,
                        steel_price_per_kg, carbon_kg_per_kg, currency, updated_at
                    )
                    SELECT id, 12000, 1000, 0, 0, 0, 'TRY', ? FROM projects
                    """,
                    (now,),
                )
                connection.execute("PRAGMA user_version = 2")
                version = 2
            if version < 3:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS inventory_movements (
                        id TEXT PRIMARY KEY,
                        project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                        stock_code TEXT NOT NULL,
                        movement_type TEXT NOT NULL,
                        diameter_mm INTEGER NOT NULL,
                        length_mm INTEGER NOT NULL,
                        run_id TEXT,
                        details_json TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_movements_project_created
                        ON inventory_movements(project_id, created_at DESC);
                    """
                )
                connection.execute("PRAGMA user_version = 3")
                version = 3
            if version < 4:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        id TEXT PRIMARY KEY,
                        username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                        password_hash TEXT NOT NULL,
                        password_salt TEXT NOT NULL,
                        role TEXT NOT NULL CHECK (role IN ('admin', 'engineer', 'store', 'viewer')),
                        active INTEGER NOT NULL DEFAULT 1,
                        created_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS sessions (
                        token_hash TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        expires_at TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_sessions_user
                        ON sessions(user_id, expires_at);
                    """
                )
                connection.execute("PRAGMA user_version = 4")
                version = 4
            if version < 5:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS project_demands (
                        id TEXT PRIMARY KEY,
                        project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                        mark TEXT NOT NULL,
                        diameter_mm INTEGER NOT NULL CHECK (diameter_mm > 0),
                        length_mm INTEGER NOT NULL CHECK (length_mm > 0),
                        quantity INTEGER NOT NULL CHECK (quantity > 0),
                        phase INTEGER NOT NULL CHECK (phase >= 0),
                        position INTEGER NOT NULL CHECK (position >= 0)
                    );

                    CREATE INDEX IF NOT EXISTS idx_project_demands_position
                        ON project_demands(project_id, position);
                    """
                )
                connection.execute("PRAGMA user_version = 5")
            connection.commit()

    def create_project(self, name: str, site: str = "", description: str = "") -> ProjectRecord:
        now = self._now()
        project_id = str(uuid4())
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO projects(id, name, site, description, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (project_id, name.strip(), site.strip(), description.strip(), now, now),
            )
            connection.execute(
                """
                INSERT INTO project_settings(
                    project_id, stock_length_mm, min_reusable_mm, kerf_mm,
                    steel_price_per_kg, carbon_kg_per_kg, currency, updated_at
                ) VALUES (?, 12000, 1000, 0, 0, 0, 'TRY', ?)
                """,
                (project_id, now),
            )
            connection.commit()
        project = self.get_project(project_id)
        if project is None:
            raise RuntimeError("project could not be created")
        return project

    def list_projects(self) -> list[ProjectRecord]:
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM projects ORDER BY updated_at DESC, name"
            ).fetchall()
        return [self._project(row) for row in rows]

    def get_project(self, project_id: str) -> ProjectRecord | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM projects WHERE id = ?", (project_id,)
            ).fetchone()
        return self._project(row) if row else None

    def get_project_settings(self, project_id: str) -> ProjectSettingsRecord:
        if self.get_project(project_id) is None:
            raise LookupError("project not found")
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM project_settings WHERE project_id = ?", (project_id,)
            ).fetchone()
        if row is None:
            raise RuntimeError("project settings are missing")
        return ProjectSettingsRecord(**dict(row))

    def update_project_settings(
        self,
        project_id: str,
        *,
        stock_length_mm: int,
        min_reusable_mm: int,
        kerf_mm: int,
        steel_price_per_kg: float,
        carbon_kg_per_kg: float,
        currency: str,
    ) -> ProjectSettingsRecord:
        if min_reusable_mm > stock_length_mm:
            raise ValueError("minimum reusable length cannot exceed stock length")
        now = self._now()
        with self.connection() as connection:
            updated = connection.execute(
                """
                UPDATE project_settings SET
                    stock_length_mm = ?, min_reusable_mm = ?, kerf_mm = ?,
                    steel_price_per_kg = ?, carbon_kg_per_kg = ?,
                    currency = ?, updated_at = ?
                WHERE project_id = ?
                """,
                (
                    stock_length_mm,
                    min_reusable_mm,
                    kerf_mm,
                    steel_price_per_kg,
                    carbon_kg_per_kg,
                    currency.strip().upper(),
                    now,
                    project_id,
                ),
            )
            if updated.rowcount == 0:
                connection.rollback()
                raise LookupError("project not found")
            connection.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?", (now, project_id)
            )
            connection.commit()
        return self.get_project_settings(project_id)

    def replace_project_demands(
        self,
        project_id: str,
        demands: Iterable[dict[str, Any]],
    ) -> list[ProjectDemandRecord]:
        if self.get_project(project_id) is None:
            raise LookupError("project not found")
        materialized = list(demands)
        if len(materialized) > 10_000:
            raise ValueError("project demand limit exceeded")
        now = self._now()
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM project_demands WHERE project_id = ?",
                (project_id,),
            )
            for position, demand in enumerate(materialized):
                mark = str(demand["mark"]).strip()
                diameter_mm = int(demand["diameter_mm"])
                length_mm = int(demand["length_mm"])
                quantity = int(demand["quantity"])
                phase = int(demand.get("phase", 0))
                if not mark:
                    connection.rollback()
                    raise ValueError("demand mark cannot be empty")
                if diameter_mm <= 0 or length_mm <= 0 or quantity <= 0 or phase < 0:
                    connection.rollback()
                    raise ValueError("project demand values are invalid")
                connection.execute(
                    """
                    INSERT INTO project_demands(
                        id, project_id, mark, diameter_mm, length_mm,
                        quantity, phase, position
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid4()),
                        project_id,
                        mark,
                        diameter_mm,
                        length_mm,
                        quantity,
                        phase,
                        position,
                    ),
                )
            connection.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (now, project_id),
            )
            connection.commit()
        return self.list_project_demands(project_id)

    def list_project_demands(self, project_id: str) -> list[ProjectDemandRecord]:
        if self.get_project(project_id) is None:
            raise LookupError("project not found")
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM project_demands
                WHERE project_id = ?
                ORDER BY position, rowid
                """,
                (project_id,),
            ).fetchall()
        return [ProjectDemandRecord(**dict(row)) for row in rows]

    def replace_available_remnants(
        self,
        project_id: str,
        items: Iterable[dict[str, Any]],
        actor: str = "system",
    ) -> list[RemnantRecord]:
        if self.get_project(project_id) is None:
            raise LookupError("project not found")

        materialized = list(items)
        codes = [str(item["stock_code"]).strip() for item in materialized]
        normalized_codes = [code.casefold() for code in codes]
        if any(not code for code in codes):
            raise ValueError("stock code cannot be empty")
        if len(normalized_codes) != len(set(normalized_codes)):
            raise ValueError("stock codes must be unique within a project")

        now = self._now()
        with self.connection() as connection:
            previous = connection.execute(
                """
                SELECT * FROM remnants
                WHERE project_id = ? AND status = 'available'
                """,
                (project_id,),
            ).fetchall()
            unavailable_codes = {
                row["stock_code"].casefold()
                for row in connection.execute(
                    """
                    SELECT stock_code FROM remnants
                    WHERE project_id = ? AND status <> 'available'
                    """,
                    (project_id,),
                ).fetchall()
            }
            reused_codes = set(normalized_codes) & unavailable_codes
            if reused_codes:
                raise ValueError("stock codes cannot reuse reserved or historical inventory")

            previous_by_code = {row["stock_code"].casefold(): row for row in previous}
            incoming_codes = set(normalized_codes)
            for normalized, row in previous_by_code.items():
                if normalized in incoming_codes:
                    continue
                self._insert_movement(
                    connection,
                    project_id=project_id,
                    stock_code=row["stock_code"],
                    movement_type="inventory_removed",
                    diameter_mm=row["diameter_mm"],
                    length_mm=row["length_mm"],
                    run_id=None,
                    details={"reason": "inventory replacement", "actor": actor},
                    created_at=now,
                )
                connection.execute("DELETE FROM remnants WHERE id = ?", (row["id"],))

            for item in materialized:
                stock_code = str(item["stock_code"]).strip()
                diameter_mm = int(item["diameter_mm"])
                length_mm = int(item["length_mm"])
                steel_grade = str(item.get("steel_grade", "B420C")).strip() or "B420C"
                existing = previous_by_code.get(stock_code.casefold())
                if existing is not None:
                    changed = (
                        existing["stock_code"] != stock_code
                        or existing["diameter_mm"] != diameter_mm
                        or existing["length_mm"] != length_mm
                        or existing["steel_grade"] != steel_grade
                    )
                    if changed:
                        connection.execute(
                            """
                            UPDATE remnants
                            SET stock_code = ?, diameter_mm = ?, length_mm = ?,
                                steel_grade = ?, updated_at = ?
                            WHERE id = ?
                            """,
                            (
                                stock_code,
                                diameter_mm,
                                length_mm,
                                steel_grade,
                                now,
                                existing["id"],
                            ),
                        )
                        self._insert_movement(
                            connection,
                            project_id=project_id,
                            stock_code=stock_code,
                            movement_type="inventory_updated",
                            diameter_mm=diameter_mm,
                            length_mm=length_mm,
                            run_id=None,
                            details={
                                "previous_stock_code": existing["stock_code"],
                                "previous_diameter_mm": existing["diameter_mm"],
                                "previous_length_mm": existing["length_mm"],
                                "previous_steel_grade": existing["steel_grade"],
                                "steel_grade": steel_grade,
                                "actor": actor,
                            },
                            created_at=now,
                        )
                    continue

                item_id = str(uuid4())
                connection.execute(
                    """
                    INSERT INTO remnants(
                        id, project_id, stock_code, diameter_mm, length_mm,
                        steel_grade, status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 'available', ?, ?)
                    """,
                    (
                        item_id,
                        project_id,
                        stock_code,
                        diameter_mm,
                        length_mm,
                        steel_grade,
                        now,
                        now,
                    ),
                )
                self._insert_movement(
                    connection,
                    project_id=project_id,
                    stock_code=stock_code,
                    movement_type="inventory_added",
                    diameter_mm=diameter_mm,
                    length_mm=length_mm,
                    run_id=None,
                    details={"steel_grade": steel_grade, "actor": actor},
                    created_at=now,
                )
            connection.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?", (now, project_id)
            )
            connection.commit()
        return self.list_remnants(project_id)

    def list_remnants(self, project_id: str, status: str = "available") -> list[RemnantRecord]:
        if self.get_project(project_id) is None:
            raise LookupError("project not found")
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM remnants
                WHERE project_id = ? AND status = ?
                ORDER BY diameter_mm, length_mm DESC, stock_code
                """,
                (project_id, status),
            ).fetchall()
        return [self._remnant(row) for row in rows]

    def save_run(
        self,
        project_id: str,
        requested_mode: str,
        solver_used: str,
        piece_count: int,
        purchased_bar_count: int,
        purchase_waste_rate: float,
        request_data: dict[str, Any],
        result_data: dict[str, Any],
    ) -> OptimizationRunRecord:
        if self.get_project(project_id) is None:
            raise LookupError("project not found")
        run_id = str(uuid4())
        now = self._now()
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO optimization_runs(
                    id, project_id, requested_mode, solver_used, status,
                    piece_count, purchased_bar_count, purchase_waste_rate,
                    request_json, result_json, created_at
                ) VALUES (?, ?, ?, ?, 'draft', ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    project_id,
                    requested_mode,
                    solver_used,
                    piece_count,
                    purchased_bar_count,
                    purchase_waste_rate,
                    json.dumps(request_data, ensure_ascii=False, separators=(",", ":")),
                    json.dumps(result_data, ensure_ascii=False, separators=(",", ":")),
                    now,
                ),
            )
            connection.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?", (now, project_id)
            )
            connection.commit()
        run = self.get_run(project_id, run_id)
        if run is None:
            raise RuntimeError("optimization run could not be saved")
        return run

    def list_runs(self, project_id: str, limit: int = 20) -> list[OptimizationRunRecord]:
        if self.get_project(project_id) is None:
            raise LookupError("project not found")
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM optimization_runs
                WHERE project_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (project_id, max(1, min(limit, 100))),
            ).fetchall()
        return [self._run(row) for row in rows]

    def get_run(self, project_id: str, run_id: str) -> OptimizationRunRecord | None:
        with self.connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM optimization_runs
                WHERE project_id = ? AND id = ?
                """,
                (project_id, run_id),
            ).fetchone()
        return self._run(row) if row else None

    def export_project(self, project_id: str) -> dict[str, Any]:
        project = self.get_project(project_id)
        if project is None:
            raise LookupError("project not found")
        settings = self.get_project_settings(project_id)
        with self.connection() as connection:
            demand_rows = connection.execute(
                "SELECT * FROM project_demands WHERE project_id = ? ORDER BY position",
                (project_id,),
            ).fetchall()
            inventory_rows = connection.execute(
                "SELECT * FROM remnants WHERE project_id = ? ORDER BY created_at",
                (project_id,),
            ).fetchall()
            run_rows = connection.execute(
                "SELECT * FROM optimization_runs WHERE project_id = ? ORDER BY created_at",
                (project_id,),
            ).fetchall()
            movement_rows = connection.execute(
                "SELECT * FROM inventory_movements WHERE project_id = ? ORDER BY created_at",
                (project_id,),
            ).fetchall()

        runs = [asdict(self._run(row)) for row in run_rows]
        movements = []
        for row in movement_rows:
            data = dict(row)
            data["details"] = json.loads(data.pop("details_json"))
            movements.append(data)
        return {
            "format": "rebarflow-project-backup",
            "version": 1,
            "exported_at": self._now(),
            "project": asdict(project),
            "settings": asdict(settings),
            "demands": [dict(row) for row in demand_rows],
            "inventory": [dict(row) for row in inventory_rows],
            "runs": runs,
            "movements": movements,
        }

    def restore_project(self, backup: dict[str, Any]) -> ProjectRecord:
        if backup.get("format") != "rebarflow-project-backup" or backup.get("version") != 1:
            raise ValueError("unsupported DonatıPlan backup format")
        project_data = backup.get("project")
        settings_data = backup.get("settings")
        if not isinstance(project_data, dict) or not isinstance(settings_data, dict):
            raise ValueError("backup project or settings data is missing")
        demands = backup.get("demands", [])
        inventory = backup.get("inventory", [])
        runs = backup.get("runs", [])
        movements = backup.get("movements", [])
        if not all(isinstance(value, list) for value in (demands, inventory, runs, movements)):
            raise ValueError("backup collections are invalid")
        if (
            len(demands) > 10_000
            or len(inventory) > 100_000
            or len(runs) > 10_000
            or len(movements) > 500_000
        ):
            raise ValueError("backup exceeds safety limits")

        project_id = str(uuid4())
        now = self._now()
        run_id_map: dict[str, str] = {}
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO projects(id, name, site, description, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    f"{str(project_data.get('name', 'Geri Yüklenen Proje')).strip()} (Geri Yüklendi)",
                    str(project_data.get("site", "")),
                    str(project_data.get("description", "")),
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO project_settings(
                    project_id, stock_length_mm, min_reusable_mm, kerf_mm,
                    steel_price_per_kg, carbon_kg_per_kg, currency, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    int(settings_data.get("stock_length_mm", 12000)),
                    int(settings_data.get("min_reusable_mm", 1000)),
                    int(settings_data.get("kerf_mm", 0)),
                    float(settings_data.get("steel_price_per_kg", 0)),
                    float(settings_data.get("carbon_kg_per_kg", 0)),
                    str(settings_data.get("currency", "TRY"))[:3].upper(),
                    now,
                ),
            )

            for position, demand in enumerate(demands):
                connection.execute(
                    """
                    INSERT INTO project_demands(
                        id, project_id, mark, diameter_mm, length_mm,
                        quantity, phase, position
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid4()),
                        project_id,
                        str(demand["mark"]).strip(),
                        int(demand["diameter_mm"]),
                        int(demand["length_mm"]),
                        int(demand["quantity"]),
                        int(demand.get("phase", 0)),
                        position,
                    ),
                )

            for item in inventory:
                status = str(item.get("status", "available"))
                if status not in {"available", "reserved", "consumed", "scrap"}:
                    raise ValueError("backup contains an invalid inventory status")
                connection.execute(
                    """
                    INSERT INTO remnants(
                        id, project_id, stock_code, diameter_mm, length_mm,
                        steel_grade, status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid4()),
                        project_id,
                        str(item["stock_code"]),
                        int(item["diameter_mm"]),
                        int(item["length_mm"]),
                        str(item.get("steel_grade", "B420C")),
                        status,
                        now,
                        now,
                    ),
                )

            for run in runs:
                old_id = str(run.get("id", ""))
                new_id = str(uuid4())
                run_id_map[old_id] = new_id
                status = str(run.get("status", "draft"))
                if status not in {"draft", "committed"}:
                    status = "draft"
                connection.execute(
                    """
                    INSERT INTO optimization_runs(
                        id, project_id, requested_mode, solver_used, status,
                        piece_count, purchased_bar_count, purchase_waste_rate,
                        request_json, result_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        new_id,
                        project_id,
                        str(run.get("requested_mode", "auto")),
                        str(run.get("solver_used", "fast")),
                        status,
                        int(run.get("piece_count", 0)),
                        int(run.get("purchased_bar_count", 0)),
                        float(run.get("purchase_waste_rate", 0)),
                        json.dumps(run.get("request_data", {}), ensure_ascii=False),
                        json.dumps(run.get("result_data", {}), ensure_ascii=False),
                        now,
                    ),
                )

            for movement in movements:
                self._insert_movement(
                    connection,
                    project_id=project_id,
                    stock_code=str(movement.get("stock_code", "UNKNOWN")),
                    movement_type=str(movement.get("movement_type", "restored")),
                    diameter_mm=int(movement.get("diameter_mm", 0)),
                    length_mm=int(movement.get("length_mm", 0)),
                    run_id=run_id_map.get(str(movement.get("run_id", ""))),
                    details=dict(movement.get("details", {})),
                    created_at=now,
                )
            connection.commit()
        restored = self.get_project(project_id)
        if restored is None:
            raise RuntimeError("restored project could not be loaded")
        return restored

    def commit_run(
        self,
        project_id: str,
        run_id: str,
        min_reusable_mm: int = 1_000,
        actor: str = "system",
    ) -> CommitResult:
        """Atomically applies a draft cut plan to the physical inventory."""
        now = self._now()
        consumed = 0
        available_outputs = 0
        scrap_outputs = 0

        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            run_row = connection.execute(
                """
                SELECT * FROM optimization_runs
                WHERE project_id = ? AND id = ?
                """,
                (project_id, run_id),
            ).fetchone()
            if run_row is None:
                connection.rollback()
                raise LookupError("optimization run not found")
            if run_row["status"] == "committed":
                connection.rollback()
                raise ValueError("optimization run is already committed")

            result_data = json.loads(run_row["result_json"])
            patterns = result_data.get("patterns", [])
            consumed_codes = {
                pattern["stock_id"]
                for pattern in patterns
                if pattern.get("source") == "remnant"
            }

            grades: dict[str, str] = {}
            for stock_code in consumed_codes:
                stock_row = connection.execute(
                    """
                    SELECT id, steel_grade, diameter_mm, length_mm FROM remnants
                    WHERE project_id = ? AND stock_code = ? AND status = 'available'
                    """,
                    (project_id, stock_code),
                ).fetchone()
                if stock_row is None:
                    connection.rollback()
                    raise ValueError(
                        f"remnant '{stock_code}' is no longer available; rerun optimization"
                    )
                source_pattern = next(
                    pattern
                    for pattern in patterns
                    if pattern.get("source") == "remnant"
                    and pattern.get("stock_id") == stock_code
                )
                if (
                    stock_row["diameter_mm"] != int(source_pattern["diameter_mm"])
                    or stock_row["length_mm"] != int(source_pattern["stock_length_mm"])
                ):
                    connection.rollback()
                    raise ValueError(
                        f"remnant '{stock_code}' changed after optimization; rerun optimization"
                    )
                grades[stock_code] = stock_row["steel_grade"]
                connection.execute(
                    """
                    UPDATE remnants SET status = 'consumed', updated_at = ?
                    WHERE id = ?
                    """,
                    (now, stock_row["id"]),
                )
                self._insert_movement(
                    connection,
                    project_id=project_id,
                    stock_code=stock_code,
                    movement_type="consumed",
                    diameter_mm=stock_row["diameter_mm"],
                    length_mm=stock_row["length_mm"],
                    run_id=run_id,
                    details={"source": "optimization commit", "actor": actor},
                    created_at=now,
                )
                consumed += 1

            output_index = 0
            for pattern in patterns:
                remaining_mm = int(pattern.get("remaining_mm", 0))
                if remaining_mm <= 0:
                    continue
                output_index += 1
                status = "available" if remaining_mm >= min_reusable_mm else "scrap"
                stock_code = f"OUT-{run_id[:8].upper()}-{output_index:03d}"
                steel_grade = grades.get(pattern.get("stock_id", ""), "B420C")
                connection.execute(
                    """
                    INSERT INTO remnants(
                        id, project_id, stock_code, diameter_mm, length_mm,
                        steel_grade, status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid4()),
                        project_id,
                        stock_code,
                        int(pattern["diameter_mm"]),
                        remaining_mm,
                        steel_grade,
                        status,
                        now,
                        now,
                    ),
                )
                self._insert_movement(
                    connection,
                    project_id=project_id,
                    stock_code=stock_code,
                    movement_type="output_available" if status == "available" else "output_scrap",
                    diameter_mm=int(pattern["diameter_mm"]),
                    length_mm=remaining_mm,
                    run_id=run_id,
                    details={
                        "source_stock": pattern.get("stock_id", ""),
                        "actor": actor,
                    },
                    created_at=now,
                )
                if status == "available":
                    available_outputs += 1
                else:
                    scrap_outputs += 1

            connection.execute(
                "UPDATE optimization_runs SET status = 'committed' WHERE id = ?",
                (run_id,),
            )
            connection.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?", (now, project_id)
            )
            connection.commit()

        return CommitResult(
            run_id=run_id,
            consumed_remnant_count=consumed,
            available_output_count=available_outputs,
            scrap_output_count=scrap_outputs,
        )

    def get_remnant(self, project_id: str, item_id: str) -> RemnantRecord | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM remnants WHERE project_id = ? AND id = ?",
                (project_id, item_id),
            ).fetchone()
        return self._remnant(row) if row else None

    def transition_remnant(
        self,
        project_id: str,
        item_id: str,
        target_status: str,
        note: str = "",
        actor: str = "system",
    ) -> RemnantRecord:
        allowed_targets = {"available", "reserved", "consumed", "scrap"}
        if target_status not in allowed_targets:
            raise ValueError("invalid inventory status")
        now = self._now()
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM remnants WHERE project_id = ? AND id = ?",
                (project_id, item_id),
            ).fetchone()
            if row is None:
                connection.rollback()
                raise LookupError("inventory item not found")
            current = row["status"]
            transitions = {
                "available": {"reserved", "consumed", "scrap"},
                "reserved": {"available", "consumed", "scrap"},
                "consumed": set(),
                "scrap": set(),
            }
            if target_status == current:
                connection.rollback()
                return self._remnant(row)
            if target_status not in transitions[current]:
                connection.rollback()
                raise ValueError(f"inventory transition {current} -> {target_status} is not allowed")
            connection.execute(
                "UPDATE remnants SET status = ?, updated_at = ? WHERE id = ?",
                (target_status, now, item_id),
            )
            self._insert_movement(
                connection,
                project_id=project_id,
                stock_code=row["stock_code"],
                movement_type=f"manual_{target_status}",
                diameter_mm=row["diameter_mm"],
                length_mm=row["length_mm"],
                run_id=None,
                details={"from_status": current, "note": note.strip(), "actor": actor},
                created_at=now,
            )
            connection.commit()
        updated = self.get_remnant(project_id, item_id)
        if updated is None:
            raise RuntimeError("inventory transition could not be loaded")
        return updated

    def list_movements(
        self,
        project_id: str,
        limit: int = 100,
    ) -> list[InventoryMovementRecord]:
        if self.get_project(project_id) is None:
            raise LookupError("project not found")
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM inventory_movements
                WHERE project_id = ?
                ORDER BY created_at DESC, rowid DESC
                LIMIT ?
                """,
                (project_id, max(1, min(limit, 500))),
            ).fetchall()
        records = []
        for row in rows:
            data = dict(row)
            data["details"] = json.loads(data.pop("details_json"))
            records.append(InventoryMovementRecord(**data))
        return records

    def user_count(self) -> int:
        with self.connection() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM users").fetchone()[0])

    def list_users(self) -> list[UserRecord]:
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT id, username, role, active, created_at
                FROM users ORDER BY created_at, username
                """
            ).fetchall()
        return [
            UserRecord(
                id=row["id"],
                username=row["username"],
                role=row["role"],
                active=bool(row["active"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def create_user(self, username: str, password: str, role: str) -> UserRecord:
        username = username.strip()
        if len(username) < 3:
            raise ValueError("username must contain at least 3 characters")
        if len(password) < 10:
            raise ValueError("password must contain at least 10 characters")
        if role not in {"admin", "engineer", "store", "viewer"}:
            raise ValueError("invalid user role")
        salt = secrets.token_bytes(16)
        digest = self._password_digest(password, salt)
        user_id = str(uuid4())
        now = self._now()
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO users(
                    id, username, password_hash, password_salt, role, active, created_at
                ) VALUES (?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    user_id,
                    username,
                    base64.b64encode(digest).decode("ascii"),
                    base64.b64encode(salt).decode("ascii"),
                    role,
                    now,
                ),
            )
            connection.commit()
        return UserRecord(user_id, username, role, True, now)

    def bootstrap_admin(self, username: str, password: str) -> UserRecord:
        if self.user_count() != 0:
            raise ValueError("administrator has already been configured")
        return self.create_user(username, password, "admin")

    def authenticate_user(self, username: str, password: str) -> UserRecord | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE username = ? COLLATE NOCASE AND active = 1",
                (username.strip(),),
            ).fetchone()
        if row is None:
            return None
        salt = base64.b64decode(row["password_salt"])
        expected = base64.b64decode(row["password_hash"])
        if not hmac.compare_digest(self._password_digest(password, salt), expected):
            return None
        return UserRecord(
            id=row["id"],
            username=row["username"],
            role=row["role"],
            active=bool(row["active"]),
            created_at=row["created_at"],
        )

    def create_session(self, user_id: str, lifetime_hours: int = 12) -> str:
        from datetime import timedelta

        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        now_value = datetime.now(UTC)
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO sessions(token_hash, user_id, expires_at, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    token_hash,
                    user_id,
                    (now_value + timedelta(hours=lifetime_hours)).isoformat(timespec="seconds"),
                    now_value.isoformat(timespec="seconds"),
                ),
            )
            connection.commit()
        return token

    def user_for_session(self, token: str | None) -> UserRecord | None:
        if not token:
            return None
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        now = self._now()
        with self.connection() as connection:
            row = connection.execute(
                """
                SELECT u.id, u.username, u.role, u.active, u.created_at
                FROM sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token_hash = ? AND s.expires_at > ? AND u.active = 1
                """,
                (token_hash, now),
            ).fetchone()
        if row is None:
            return None
        return UserRecord(
            id=row["id"],
            username=row["username"],
            role=row["role"],
            active=bool(row["active"]),
            created_at=row["created_at"],
        )

    def delete_session(self, token: str | None) -> None:
        if not token:
            return
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with self.connection() as connection:
            connection.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
            connection.commit()

    @staticmethod
    def _password_digest(password: str, salt: bytes) -> bytes:
        return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310_000)

    @staticmethod
    def _insert_movement(
        connection: sqlite3.Connection,
        *,
        project_id: str,
        stock_code: str,
        movement_type: str,
        diameter_mm: int,
        length_mm: int,
        run_id: str | None,
        details: dict[str, Any],
        created_at: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO inventory_movements(
                id, project_id, stock_code, movement_type, diameter_mm,
                length_mm, run_id, details_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                project_id,
                stock_code,
                movement_type,
                diameter_mm,
                length_mm,
                run_id,
                json.dumps(details, ensure_ascii=False, separators=(",", ":")),
                created_at,
            ),
        )

    @staticmethod
    def _project(row: sqlite3.Row) -> ProjectRecord:
        return ProjectRecord(**dict(row))

    @staticmethod
    def _remnant(row: sqlite3.Row) -> RemnantRecord:
        return RemnantRecord(**dict(row))

    @staticmethod
    def _run(row: sqlite3.Row) -> OptimizationRunRecord:
        data = dict(row)
        data["request_data"] = json.loads(data.pop("request_json"))
        data["result_data"] = json.loads(data.pop("result_json"))
        return OptimizationRunRecord(**data)

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat(timespec="seconds")


def default_database_path() -> Path:
    configured = os.getenv("REBARFLOW_DATABASE_PATH", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "data" / "rebarflow.db"
