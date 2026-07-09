from __future__ import annotations

import base64
import binascii
import os
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from .models import CutDemand, StockPiece, StockSource
from .reports import ReportBuilder
from .importers import CsvDemandImporter, XlsxDemandImporter
from .service import OptimizationMode, OptimizationService
from .store import SqliteStore, default_database_path


PositiveInt = Annotated[int, Field(gt=0)]
NonNegativeInt = Annotated[int, Field(ge=0)]


class DemandInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mark: str = Field(min_length=1, max_length=80)
    diameter_mm: PositiveInt
    length_mm: PositiveInt
    quantity: PositiveInt
    phase: NonNegativeInt = 0


class ProjectDemandsReplaceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    demands: list[DemandInput] = Field(default_factory=list, max_length=10_000)


class RemnantInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=80)
    diameter_mm: PositiveInt
    length_mm: PositiveInt


class OptimizationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    demands: list[DemandInput] = Field(min_length=1, max_length=500)
    remnants: list[RemnantInput] = Field(default_factory=list, max_length=5_000)
    mode: Literal["auto", "exact", "advanced", "fast"] = "auto"


class CutOutput(BaseModel):
    mark: str
    length_mm: int
    phase: int


class PatternOutput(BaseModel):
    stock_id: str
    diameter_mm: int
    stock_length_mm: int
    source: str
    cuts: list[CutOutput]
    remaining_mm: int
    kerf_loss_mm: int


class SummaryOutput(BaseModel):
    piece_count: int
    purchased_bar_count: int
    demand_length_mm: int
    purchased_length_mm: int
    used_source_length_mm: int
    new_stock_waste_mm: int
    total_waste_mm: int
    remnant_input_used_mm: int
    remnant_source_used_mm: int
    reusable_output_mm: int
    scrap_output_mm: int
    real_scrap_mm: int
    kerf_loss_mm: int
    new_stock_waste_rate: float
    waste_rate: float
    real_scrap_rate: float
    purchase_waste_rate: float
    demand_weight_kg: float
    purchased_weight_kg: float
    estimated_cost: float
    estimated_carbon_kg: float
    currency: str


class ReusableRemnantOutput(BaseModel):
    source_stock_id: str
    diameter_mm: int
    length_mm: int
    source: str
    note: str


class ComparisonOutput(BaseModel):
    baseline_solver: str
    optimized_solver: str
    baseline_bar_count: int
    optimized_bar_count: int
    saved_bar_count: int
    saved_weight_kg: float
    saved_cost: float
    saved_carbon_kg: float


class OptimizationResponse(BaseModel):
    run_id: str | None = None
    requested_mode: str
    solver_used: str
    summary: SummaryOutput
    patterns: list[PatternOutput]
    reusable_remnants: list[ReusableRemnantOutput]
    comparison: ComparisonOutput | None = None


class CsvImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=5_000_000)


class XlsxImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: str = Field(min_length=1, max_length=255)
    content_base64: str = Field(min_length=1, max_length=20_000_000)


class ImportIssueOutput(BaseModel):
    row: int
    field: str
    message: str


class CsvImportResponse(BaseModel):
    accepted_count: int
    rejected_count: int
    demands: list[DemandInput]
    issues: list[ImportIssueOutput]


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=120)
    site: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=2000)


class ProjectOutput(BaseModel):
    id: str
    name: str
    site: str
    description: str
    created_at: str
    updated_at: str


class ProjectSettingsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stock_length_mm: PositiveInt = 12_000
    min_reusable_mm: NonNegativeInt = 1_000
    kerf_mm: NonNegativeInt = 0
    steel_price_per_kg: Annotated[float, Field(ge=0)] = 0
    carbon_kg_per_kg: Annotated[float, Field(ge=0)] = 0
    currency: str = Field(default="TRY", min_length=3, max_length=3)


class ProjectSettingsOutput(ProjectSettingsInput):
    project_id: str
    updated_at: str


class BackupRestoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    backup: dict


class AuthCredentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=10, max_length=256)


class UserCreate(AuthCredentials):
    role: Literal["admin", "engineer", "store", "viewer"]


class UserOutput(BaseModel):
    id: str
    username: str
    role: str
    active: bool
    created_at: str


class AuthStatusOutput(BaseModel):
    setup_required: bool
    authenticated: bool
    user: UserOutput | None


class InventoryItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stock_code: str = Field(min_length=1, max_length=80)
    diameter_mm: PositiveInt
    length_mm: PositiveInt
    steel_grade: str = Field(default="B420C", min_length=1, max_length=30)


class InventoryReplaceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[InventoryItemInput] = Field(default_factory=list, max_length=5000)


class InventoryItemOutput(BaseModel):
    id: str
    project_id: str
    stock_code: str
    diameter_mm: int
    length_mm: int
    steel_grade: str
    status: str
    created_at: str
    updated_at: str


class InventoryMovementOutput(BaseModel):
    id: str
    project_id: str
    stock_code: str
    movement_type: str
    diameter_mm: int
    length_mm: int
    run_id: str | None
    details: dict
    created_at: str


class InventoryTransitionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_status: Literal["available", "reserved", "consumed", "scrap"]
    note: str = Field(default="", max_length=500)


class RunSummaryOutput(BaseModel):
    id: str
    project_id: str
    requested_mode: str
    solver_used: str
    status: str
    piece_count: int
    purchased_bar_count: int
    purchase_waste_rate: float
    created_at: str


class CommitRunOutput(BaseModel):
    run_id: str
    consumed_remnant_count: int
    available_output_count: int
    scrap_output_count: int


service = OptimizationService()
csv_importer = CsvDemandImporter()
xlsx_importer = XlsxDemandImporter()
report_builder = ReportBuilder()
app = FastAPI(
    title="DonatıPlan API",
    version="0.1.0",
    description="Donatı kesim ve artık parça yeniden kullanım optimizasyon servisi.",
)
app.state.store = SqliteStore(default_database_path())
allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "REBARFLOW_ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Content-Type"],
)


def _security_headers(response: Response) -> Response:
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response


@app.middleware("http")
async def authentication_and_security(request: Request, call_next):
    path = request.url.path
    if request.method == "OPTIONS":
        return _security_headers(await call_next(request))
    if not path.startswith("/api/v1") or path in {
        "/api/v1/health",
        "/api/v1/auth/status",
        "/api/v1/auth/bootstrap",
        "/api/v1/auth/login",
    }:
        return _security_headers(await call_next(request))

    store: SqliteStore = request.app.state.store
    if store.user_count() == 0:
        request.state.user = None
        return _security_headers(await call_next(request))

    token = request.cookies.get("rebarflow_session")
    user = store.user_for_session(token)
    if user is None:
        return _security_headers(
            JSONResponse(status_code=401, content={"detail": "authentication required"})
        )
    request.state.user = user

    if "/users" in path and user.role != "admin":
        return _security_headers(
            JSONResponse(status_code=403, content={"detail": "administrator role required"})
        )

    is_logout = path.endswith("/auth/logout")
    if request.method not in {"GET", "HEAD", "OPTIONS"} and not is_logout:
        if user.role == "viewer":
            return _security_headers(
                JSONResponse(status_code=403, content={"detail": "read-only role"})
            )
        if ("/users" in path or "/backups/restore" in path) and user.role != "admin":
            return _security_headers(
                JSONResponse(status_code=403, content={"detail": "administrator role required"})
            )
        if user.role == "store" and not (
            "/inventory" in path or path.endswith("/commit") or path.endswith("/auth/logout")
        ):
            return _security_headers(
                JSONResponse(status_code=403, content={"detail": "engineer role required"})
            )
    return _security_headers(await call_next(request))


@app.exception_handler(ValueError)
async def value_error_handler(_: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(LookupError)
async def lookup_error_handler(_: Request, exc: LookupError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(sqlite3.IntegrityError)
async def integrity_error_handler(_: Request, exc: sqlite3.IntegrityError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": f"database conflict: {exc}"})


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "rebarflow-api"}


@app.get("/api/v1/auth/status", response_model=AuthStatusOutput)
def auth_status(request: Request) -> AuthStatusOutput:
    store: SqliteStore = request.app.state.store
    setup_required = store.user_count() == 0
    user = None if setup_required else store.user_for_session(
        request.cookies.get("rebarflow_session")
    )
    return AuthStatusOutput(
        setup_required=setup_required,
        authenticated=user is not None,
        user=UserOutput(**asdict(user)) if user else None,
    )


def _set_session_cookie(response: JSONResponse, token: str) -> None:
    response.set_cookie(
        "rebarflow_session",
        token,
        max_age=12 * 60 * 60,
        httponly=True,
        samesite="lax",
        secure=os.getenv("REBARFLOW_SECURE_COOKIE", "0") == "1",
        path="/",
    )


def _actor_name(request: Request) -> str:
    user = getattr(request.state, "user", None)
    return user.username if user is not None else "local"


@app.post("/api/v1/auth/bootstrap", response_model=UserOutput, status_code=201)
def bootstrap_admin(payload: AuthCredentials, request: Request) -> JSONResponse:
    store: SqliteStore = request.app.state.store
    user = store.bootstrap_admin(payload.username, payload.password)
    token = store.create_session(user.id)
    response = JSONResponse(status_code=201, content=UserOutput(**asdict(user)).model_dump())
    _set_session_cookie(response, token)
    return response


@app.post("/api/v1/auth/login", response_model=UserOutput)
def login(payload: AuthCredentials, request: Request) -> JSONResponse:
    store: SqliteStore = request.app.state.store
    user = store.authenticate_user(payload.username, payload.password)
    if user is None:
        return JSONResponse(status_code=401, content={"detail": "invalid username or password"})
    token = store.create_session(user.id)
    response = JSONResponse(content=UserOutput(**asdict(user)).model_dump())
    _set_session_cookie(response, token)
    return response


@app.post("/api/v1/auth/logout")
def logout(request: Request) -> JSONResponse:
    store: SqliteStore = request.app.state.store
    store.delete_session(request.cookies.get("rebarflow_session"))
    response = JSONResponse(content={"status": "ok"})
    response.delete_cookie("rebarflow_session", path="/")
    return response


@app.post("/api/v1/users", response_model=UserOutput, status_code=201)
def create_user(payload: UserCreate, request: Request) -> UserOutput:
    store: SqliteStore = request.app.state.store
    return UserOutput(**asdict(store.create_user(payload.username, payload.password, payload.role)))


@app.get("/api/v1/users", response_model=list[UserOutput])
def list_users(request: Request) -> list[UserOutput]:
    store: SqliteStore = request.app.state.store
    return [UserOutput(**asdict(user)) for user in store.list_users()]


@app.get("/api/v1/projects", response_model=list[ProjectOutput])
def list_projects(request: Request) -> list[ProjectOutput]:
    store: SqliteStore = request.app.state.store
    return [ProjectOutput(**asdict(record)) for record in store.list_projects()]


@app.post("/api/v1/projects", response_model=ProjectOutput, status_code=201)
def create_project(payload: ProjectCreate, request: Request) -> ProjectOutput:
    store: SqliteStore = request.app.state.store
    record = store.create_project(payload.name, payload.site, payload.description)
    return ProjectOutput(**asdict(record))


@app.get("/api/v1/projects/{project_id}", response_model=ProjectOutput)
def get_project(project_id: str, request: Request) -> ProjectOutput:
    store: SqliteStore = request.app.state.store
    record = store.get_project(project_id)
    if record is None:
        raise LookupError("project not found")
    return ProjectOutput(**asdict(record))


@app.get(
    "/api/v1/projects/{project_id}/settings",
    response_model=ProjectSettingsOutput,
)
def get_project_settings(project_id: str, request: Request) -> ProjectSettingsOutput:
    store: SqliteStore = request.app.state.store
    return ProjectSettingsOutput(**asdict(store.get_project_settings(project_id)))


@app.put(
    "/api/v1/projects/{project_id}/settings",
    response_model=ProjectSettingsOutput,
)
def update_project_settings(
    project_id: str,
    payload: ProjectSettingsInput,
    request: Request,
) -> ProjectSettingsOutput:
    store: SqliteStore = request.app.state.store
    record = store.update_project_settings(project_id, **payload.model_dump())
    return ProjectSettingsOutput(**asdict(record))


@app.get(
    "/api/v1/projects/{project_id}/demands",
    response_model=list[DemandInput],
)
def list_project_demands(project_id: str, request: Request) -> list[DemandInput]:
    store: SqliteStore = request.app.state.store
    return [
        DemandInput(
            mark=record.mark,
            diameter_mm=record.diameter_mm,
            length_mm=record.length_mm,
            quantity=record.quantity,
            phase=record.phase,
        )
        for record in store.list_project_demands(project_id)
    ]


@app.put(
    "/api/v1/projects/{project_id}/demands",
    response_model=list[DemandInput],
)
def replace_project_demands(
    project_id: str,
    payload: ProjectDemandsReplaceRequest,
    request: Request,
) -> list[DemandInput]:
    store: SqliteStore = request.app.state.store
    records = store.replace_project_demands(
        project_id,
        [item.model_dump() for item in payload.demands],
    )
    return [
        DemandInput(
            mark=record.mark,
            diameter_mm=record.diameter_mm,
            length_mm=record.length_mm,
            quantity=record.quantity,
            phase=record.phase,
        )
        for record in records
    ]


@app.get("/api/v1/projects/{project_id}/backup.json")
def download_project_backup(project_id: str, request: Request) -> JSONResponse:
    store: SqliteStore = request.app.state.store
    backup = store.export_project(project_id)
    return JSONResponse(
        content=backup,
        headers={
            "Content-Disposition": f'attachment; filename="DonatiPlan-Backup-{project_id[:8]}.json"'
        },
    )


@app.post("/api/v1/backups/restore", response_model=ProjectOutput, status_code=201)
def restore_project_backup(
    payload: BackupRestoreRequest,
    request: Request,
) -> ProjectOutput:
    store: SqliteStore = request.app.state.store
    return ProjectOutput(**asdict(store.restore_project(payload.backup)))


@app.get(
    "/api/v1/projects/{project_id}/inventory",
    response_model=list[InventoryItemOutput],
)
def list_inventory(project_id: str, request: Request) -> list[InventoryItemOutput]:
    store: SqliteStore = request.app.state.store
    return [
        InventoryItemOutput(**asdict(record))
        for record in store.list_remnants(project_id)
    ]


@app.get(
    "/api/v1/projects/{project_id}/inventory/{item_id}",
    response_model=InventoryItemOutput,
)
def get_inventory_item(
    project_id: str,
    item_id: str,
    request: Request,
) -> InventoryItemOutput:
    store: SqliteStore = request.app.state.store
    record = store.get_remnant(project_id, item_id)
    if record is None:
        raise LookupError("inventory item not found")
    return InventoryItemOutput(**asdict(record))


@app.post(
    "/api/v1/projects/{project_id}/inventory/{item_id}/transition",
    response_model=InventoryItemOutput,
)
def transition_inventory_item(
    project_id: str,
    item_id: str,
    payload: InventoryTransitionInput,
    request: Request,
) -> InventoryItemOutput:
    store: SqliteStore = request.app.state.store
    return InventoryItemOutput(
        **asdict(
            store.transition_remnant(
                project_id,
                item_id,
                payload.target_status,
                payload.note,
                actor=_actor_name(request),
            )
        )
    )


@app.get("/api/v1/projects/{project_id}/inventory/{item_id}/qr.png")
def download_inventory_qr(
    project_id: str,
    item_id: str,
    request: Request,
) -> Response:
    store: SqliteStore = request.app.state.store
    project = store.get_project(project_id)
    item = store.get_remnant(project_id, item_id)
    if project is None or item is None:
        raise LookupError("inventory item not found")
    return Response(
        content=report_builder.build_inventory_qr_png(project, item),
        media_type="image/png",
        headers={"Content-Disposition": f'inline; filename="QR-{item.stock_code}.png"'},
    )


@app.get("/api/v1/projects/{project_id}/inventory-labels.pdf")
def download_inventory_labels(project_id: str, request: Request) -> Response:
    store: SqliteStore = request.app.state.store
    project = store.get_project(project_id)
    if project is None:
        raise LookupError("project not found")
    inventory = store.list_remnants(project_id)
    return Response(
        content=report_builder.build_inventory_labels_pdf(project, inventory),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="DonatiPlan-QR-Etiketleri.pdf"'},
    )


@app.get(
    "/api/v1/projects/{project_id}/movements",
    response_model=list[InventoryMovementOutput],
)
def list_inventory_movements(
    project_id: str,
    request: Request,
    limit: int = 100,
) -> list[InventoryMovementOutput]:
    store: SqliteStore = request.app.state.store
    return [
        InventoryMovementOutput(**asdict(record))
        for record in store.list_movements(project_id, limit)
    ]


@app.put(
    "/api/v1/projects/{project_id}/inventory",
    response_model=list[InventoryItemOutput],
)
def replace_inventory(
    project_id: str,
    payload: InventoryReplaceRequest,
    request: Request,
) -> list[InventoryItemOutput]:
    store: SqliteStore = request.app.state.store
    records = store.replace_available_remnants(
        project_id,
        [item.model_dump() for item in payload.items],
        actor=_actor_name(request),
    )
    return [InventoryItemOutput(**asdict(record)) for record in records]


@app.get(
    "/api/v1/projects/{project_id}/runs",
    response_model=list[RunSummaryOutput],
)
def list_project_runs(
    project_id: str,
    request: Request,
    limit: int = 20,
) -> list[RunSummaryOutput]:
    store: SqliteStore = request.app.state.store
    return [
        RunSummaryOutput(
            id=record.id,
            project_id=record.project_id,
            requested_mode=record.requested_mode,
            solver_used=record.solver_used,
            status=record.status,
            piece_count=record.piece_count,
            purchased_bar_count=record.purchased_bar_count,
            purchase_waste_rate=record.purchase_waste_rate,
            created_at=record.created_at,
        )
        for record in store.list_runs(project_id, limit)
    ]


@app.post(
    "/api/v1/projects/{project_id}/runs/{run_id}/commit",
    response_model=CommitRunOutput,
)
def commit_project_run(
    project_id: str,
    run_id: str,
    request: Request,
) -> CommitRunOutput:
    store: SqliteStore = request.app.state.store
    settings = store.get_project_settings(project_id)
    result = store.commit_run(
        project_id,
        run_id,
        min_reusable_mm=settings.min_reusable_mm,
        actor=_actor_name(request),
    )
    return CommitRunOutput(
        run_id=result.run_id,
        consumed_remnant_count=result.consumed_remnant_count,
        available_output_count=result.available_output_count,
        scrap_output_count=result.scrap_output_count,
    )


def _report_context(project_id: str, run_id: str, store: SqliteStore):
    project = store.get_project(project_id)
    if project is None:
        raise LookupError("project not found")
    run = store.get_run(project_id, run_id)
    if run is None:
        raise LookupError("optimization run not found")
    settings = store.get_project_settings(project_id)
    inventory = store.list_remnants(project_id)
    return project, settings, run, inventory


@app.get("/api/v1/projects/{project_id}/runs/{run_id}/report.xlsx")
def download_run_xlsx(project_id: str, run_id: str, request: Request) -> Response:
    store: SqliteStore = request.app.state.store
    project, settings, run, inventory = _report_context(project_id, run_id, store)
    content = report_builder.build_xlsx(project, settings, run, inventory)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="DonatiPlan-{run_id[:8]}.xlsx"'
        },
    )


@app.get("/api/v1/projects/{project_id}/runs/{run_id}/report.pdf")
def download_run_pdf(project_id: str, run_id: str, request: Request) -> Response:
    store: SqliteStore = request.app.state.store
    project, settings, run, _ = _report_context(project_id, run_id, store)
    content = report_builder.build_pdf(project, settings, run)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="DonatiPlan-{run_id[:8]}.pdf"'
        },
    )


@app.post("/api/v1/import/csv", response_model=CsvImportResponse)
def import_csv(payload: CsvImportRequest) -> CsvImportResponse:
    result = csv_importer.import_text(payload.content)
    return CsvImportResponse(
        accepted_count=result.accepted_count,
        rejected_count=result.rejected_count,
        demands=[
            DemandInput(
                mark=demand.mark,
                diameter_mm=demand.diameter_mm,
                length_mm=demand.length_mm,
                quantity=demand.quantity,
                phase=demand.phase,
            )
            for demand in result.demands
        ],
        issues=[
            ImportIssueOutput(row=issue.row, field=issue.field, message=issue.message)
            for issue in result.issues
        ],
    )


@app.post("/api/v1/import/xlsx", response_model=CsvImportResponse)
def import_xlsx(payload: XlsxImportRequest) -> CsvImportResponse:
    if not payload.filename.lower().endswith(".xlsx"):
        raise ValueError("only .xlsx files are accepted")
    try:
        content = base64.b64decode(payload.content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("invalid base64 XLSX content") from exc
    result = xlsx_importer.import_bytes(content)
    return CsvImportResponse(
        accepted_count=result.accepted_count,
        rejected_count=result.rejected_count,
        demands=[
            DemandInput(
                mark=demand.mark,
                diameter_mm=demand.diameter_mm,
                length_mm=demand.length_mm,
                quantity=demand.quantity,
                phase=demand.phase,
            )
            for demand in result.demands
        ],
        issues=[
            ImportIssueOutput(row=issue.row, field=issue.field, message=issue.message)
            for issue in result.issues
        ],
    )


@app.get("/api/v1/templates/bbs.xlsx", response_class=FileResponse)
def download_bbs_template() -> FileResponse:
    template = Path(__file__).resolve().parents[2] / "assets" / "RebarFlow-BBS-Sablonu.xlsx"
    if not template.exists():
        raise LookupError("BBS template is missing")
    return FileResponse(
        template,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="DonatiPlan-BBS-Sablonu.xlsx",
    )


@app.post("/api/v1/optimize", response_model=OptimizationResponse)
def optimize(payload: OptimizationRequest) -> OptimizationResponse:
    return _optimize(payload)


@app.post(
    "/api/v1/projects/{project_id}/optimize",
    response_model=OptimizationResponse,
)
def optimize_project(
    project_id: str,
    payload: OptimizationRequest,
    request: Request,
) -> OptimizationResponse:
    store: SqliteStore = request.app.state.store
    if store.get_project(project_id) is None:
        raise LookupError("project not found")
    settings = store.get_project_settings(project_id)
    project_service = OptimizationService(
        stock_length_mm=settings.stock_length_mm,
        min_reusable_mm=settings.min_reusable_mm,
        kerf_mm=settings.kerf_mm,
    )
    response = _optimize(
        payload,
        project_service,
        steel_price_per_kg=settings.steel_price_per_kg,
        carbon_kg_per_kg=settings.carbon_kg_per_kg,
        currency=settings.currency,
    )
    baseline_payload = payload.model_copy(update={"mode": "fast"})
    baseline = _optimize(
        baseline_payload,
        project_service,
        steel_price_per_kg=settings.steel_price_per_kg,
        carbon_kg_per_kg=settings.carbon_kg_per_kg,
        currency=settings.currency,
    )
    saved_weight = max(
        0.0,
        baseline.summary.purchased_weight_kg - response.summary.purchased_weight_kg,
    )
    response = response.model_copy(
        update={
            "comparison": ComparisonOutput(
                baseline_solver=baseline.solver_used,
                optimized_solver=response.solver_used,
                baseline_bar_count=baseline.summary.purchased_bar_count,
                optimized_bar_count=response.summary.purchased_bar_count,
                saved_bar_count=max(
                    0,
                    baseline.summary.purchased_bar_count - response.summary.purchased_bar_count,
                ),
                saved_weight_kg=saved_weight,
                saved_cost=saved_weight * settings.steel_price_per_kg,
                saved_carbon_kg=saved_weight * settings.carbon_kg_per_kg,
            )
        }
    )
    run = store.save_run(
        project_id=project_id,
        requested_mode=response.requested_mode,
        solver_used=response.solver_used,
        piece_count=response.summary.piece_count,
        purchased_bar_count=response.summary.purchased_bar_count,
        purchase_waste_rate=response.summary.waste_rate,
        request_data=payload.model_dump(),
        result_data=response.model_dump(exclude={"run_id"}),
    )
    return response.model_copy(update={"run_id": run.id})


def _optimize(
    payload: OptimizationRequest,
    optimizer_service: OptimizationService = service,
    steel_price_per_kg: float = 0,
    carbon_kg_per_kg: float = 0,
    currency: str = "TRY",
) -> OptimizationResponse:
    demands = [
        CutDemand(
            mark=item.mark,
            diameter_mm=item.diameter_mm,
            length_mm=item.length_mm,
            quantity=item.quantity,
            phase=item.phase,
        )
        for item in payload.demands
    ]
    remnants = [
        StockPiece(
            id=item.id,
            diameter_mm=item.diameter_mm,
            length_mm=item.length_mm,
            source=StockSource.REMNANT,
        )
        for item in payload.remnants
    ]
    run_result = optimizer_service.run(demands, remnants, OptimizationMode(payload.mode))
    result = run_result.result
    demand_weight_kg = sum(
        demand.quantity
        * (demand.length_mm / 1000)
        * (demand.diameter_mm**2 / 162)
        for demand in demands
    )
    purchased_weight_kg = sum(
        (pattern.stock.length_mm / 1000)
        * (pattern.stock.diameter_mm**2 / 162)
        for pattern in result.patterns
        if pattern.stock.source == StockSource.NEW
    )

    return OptimizationResponse(
        run_id=None,
        requested_mode=run_result.requested_mode,
        solver_used=run_result.solver_used,
        summary=SummaryOutput(
            piece_count=run_result.piece_count,
            purchased_bar_count=result.purchased_bar_count,
            demand_length_mm=result.demand_length_mm,
            purchased_length_mm=result.purchased_length_mm,
            used_source_length_mm=result.used_source_length_mm,
            new_stock_waste_mm=result.new_stock_waste_mm,
            total_waste_mm=result.total_waste_mm,
            remnant_input_used_mm=result.remnant_input_used_mm,
            remnant_source_used_mm=result.remnant_source_used_mm,
            reusable_output_mm=result.reusable_output_mm,
            scrap_output_mm=result.scrap_output_mm,
            real_scrap_mm=result.real_scrap_mm,
            kerf_loss_mm=result.kerf_loss_mm,
            new_stock_waste_rate=result.new_stock_waste_rate,
            waste_rate=result.waste_rate,
            real_scrap_rate=result.real_scrap_rate,
            purchase_waste_rate=result.purchase_waste_rate,
            demand_weight_kg=demand_weight_kg,
            purchased_weight_kg=purchased_weight_kg,
            estimated_cost=purchased_weight_kg * steel_price_per_kg,
            estimated_carbon_kg=purchased_weight_kg * carbon_kg_per_kg,
            currency=currency,
        ),
        patterns=[
            PatternOutput(
                stock_id=pattern.stock.id,
                diameter_mm=pattern.stock.diameter_mm,
                stock_length_mm=pattern.stock.length_mm,
                source=pattern.stock.source,
                cuts=[
                    CutOutput(mark=cut.mark, length_mm=cut.length_mm, phase=cut.phase)
                    for cut in pattern.cuts
                ],
                remaining_mm=pattern.remaining_mm,
                kerf_loss_mm=pattern.kerf_loss_mm,
            )
            for pattern in result.patterns
        ],
        reusable_remnants=[
            ReusableRemnantOutput(
                source_stock_id=pattern.stock.id,
                diameter_mm=pattern.stock.diameter_mm,
                length_mm=pattern.remaining_mm,
                source=pattern.stock.source,
                note="Bu parça bu projede kullanılmadı; stokta tekrar kullanılabilir.",
            )
            for pattern in result.patterns
            if pattern.remaining_mm >= optimizer_service.fast.min_reusable_mm
            and pattern.remaining_mm > 0
        ],
        comparison=None,
    )


def run() -> None:
    import uvicorn

    uvicorn.run("rebarflow.api:app", host="127.0.0.1", port=8000, reload=False)
