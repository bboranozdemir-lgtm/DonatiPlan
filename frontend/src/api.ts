import type {
  DemandInput,
  CsvImportResponse,
  CommitResult,
  AuthStatus,
  AuthUser,
  InventoryItem,
  InventoryMovement,
  OptimizationMode,
  OptimizationResponse,
  Project,
  ProjectSettings,
  RemnantInput,
  RunSummary,
} from "./types";

const API_URL = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000/api/v1";
export const bbsTemplateUrl = `${API_URL}/templates/bbs.xlsx`;
export const reportUrl = (
  projectId: string,
  runId: string,
  format: "xlsx" | "pdf",
) => `${API_URL}/projects/${projectId}/runs/${runId}/report.${format}`;
export const inventoryLabelsUrl = (projectId: string) =>
  `${API_URL}/projects/${projectId}/inventory-labels.pdf`;
export const projectBackupUrl = (projectId: string) =>
  `${API_URL}/projects/${projectId}/backup.json`;

export async function optimize(
  demands: DemandInput[],
  remnants: RemnantInput[],
  mode: OptimizationMode,
): Promise<OptimizationResponse> {
  return requestOptimization(`${API_URL}/optimize`, demands, remnants, mode);
}

export async function optimizeProject(
  projectId: string,
  demands: DemandInput[],
  remnants: RemnantInput[],
  mode: OptimizationMode,
): Promise<OptimizationResponse> {
  return requestOptimization(
    `${API_URL}/projects/${projectId}/optimize`,
    demands,
    remnants,
    mode,
  );
}

async function requestOptimization(
  url: string,
  demands: DemandInput[],
  remnants: RemnantInput[],
  mode: OptimizationMode,
): Promise<OptimizationResponse> {
  const response = await fetch(url, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      demands: demands.map(({ id: _id, ...item }) => item),
      remnants: remnants.map(({ rowId: _rowId, ...item }) => item),
      mode,
    }),
  });

  const body = await response.json();
  if (!response.ok) {
    const detail = typeof body.detail === "string" ? body.detail : "İstek doğrulanamadı.";
    throw new Error(detail);
  }
  return body as OptimizationResponse;
}

async function requestJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, { credentials: "include", ...options });
  const body = await response.json();
  if (!response.ok) {
    const detail = typeof body.detail === "string" ? body.detail : "İşlem tamamlanamadı.";
    throw new Error(detail);
  }
  return body as T;
}

export function listProjects(): Promise<Project[]> {
  return requestJson<Project[]>(`${API_URL}/projects`);
}

export function createProject(name: string, site: string): Promise<Project> {
  return requestJson<Project>(`${API_URL}/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, site }),
  });
}

export async function restoreProjectBackup(file: File): Promise<Project> {
  let backup: unknown;
  try {
    backup = JSON.parse(await file.text());
  } catch {
    throw new Error("Yedek dosyası geçerli JSON değil.");
  }
  return requestJson<Project>(`${API_URL}/backups/restore`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ backup }),
  });
}

export function loadProjectSettings(projectId: string): Promise<ProjectSettings> {
  return requestJson<ProjectSettings>(`${API_URL}/projects/${projectId}/settings`);
}

export function loadProjectDemands(projectId: string): Promise<Omit<DemandInput, "id">[]> {
  return requestJson<Omit<DemandInput, "id">[]>(`${API_URL}/projects/${projectId}/demands`);
}

export function saveProjectDemands(
  projectId: string,
  demands: DemandInput[],
): Promise<Omit<DemandInput, "id">[]> {
  return requestJson<Omit<DemandInput, "id">[]>(`${API_URL}/projects/${projectId}/demands`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ demands: demands.map(({ id: _id, ...item }) => item) }),
  });
}

export function saveProjectSettings(
  projectId: string,
  settings: Omit<ProjectSettings, "project_id" | "updated_at">,
): Promise<ProjectSettings> {
  return requestJson<ProjectSettings>(`${API_URL}/projects/${projectId}/settings`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });
}

export function loadInventory(projectId: string): Promise<InventoryItem[]> {
  return requestJson<InventoryItem[]>(`${API_URL}/projects/${projectId}/inventory`);
}

export function getInventoryItem(
  projectId: string,
  itemId: string,
): Promise<InventoryItem> {
  return requestJson<InventoryItem>(
    `${API_URL}/projects/${projectId}/inventory/${itemId}`,
  );
}

export function transitionInventoryItem(
  projectId: string,
  itemId: string,
  targetStatus: "available" | "reserved" | "consumed" | "scrap",
  note = "",
): Promise<InventoryItem> {
  return requestJson<InventoryItem>(
    `${API_URL}/projects/${projectId}/inventory/${itemId}/transition`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target_status: targetStatus, note }),
    },
  );
}

export function loadMovements(projectId: string): Promise<InventoryMovement[]> {
  return requestJson<InventoryMovement[]>(`${API_URL}/projects/${projectId}/movements`);
}

export function saveInventory(
  projectId: string,
  remnants: RemnantInput[],
): Promise<InventoryItem[]> {
  return requestJson<InventoryItem[]>(`${API_URL}/projects/${projectId}/inventory`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      items: remnants.map((item) => ({
        stock_code: item.id,
        diameter_mm: item.diameter_mm,
        length_mm: item.length_mm,
        steel_grade: "B420C",
      })),
    }),
  });
}

export function listRuns(projectId: string): Promise<RunSummary[]> {
  return requestJson<RunSummary[]>(`${API_URL}/projects/${projectId}/runs`);
}

export function commitRun(projectId: string, runId: string): Promise<CommitResult> {
  return requestJson<CommitResult>(
    `${API_URL}/projects/${projectId}/runs/${runId}/commit`,
    { method: "POST" },
  );
}

export async function importCsv(content: string): Promise<CsvImportResponse> {
  const response = await fetch(`${API_URL}/import/csv`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  const body = await response.json();
  if (!response.ok) {
    const detail = typeof body.detail === "string" ? body.detail : "CSV dosyası okunamadı.";
    throw new Error(detail);
  }
  return body as CsvImportResponse;
}

export async function readCsvFile(file: File): Promise<string> {
  const buffer = await file.arrayBuffer();
  const tryDecode = (encoding: string) => new TextDecoder(encoding, { fatal: true }).decode(buffer);

  try {
    return tryDecode("utf-8");
  } catch {
    try {
      return tryDecode("windows-1254");
    } catch {
      throw new Error(
        "CSV dosyası UTF-8 veya Türkçe Excel/Windows-1254 olarak okunamadı. Lütfen dosyayı UTF-8 CSV ya da XLSX olarak kaydedip tekrar deneyin.",
      );
    }
  }
}

export function getAuthStatus(): Promise<AuthStatus> {
  return requestJson<AuthStatus>(`${API_URL}/auth/status`);
}

export function bootstrapAdmin(username: string, password: string): Promise<AuthUser> {
  return requestJson<AuthUser>(`${API_URL}/auth/bootstrap`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
}

export function login(username: string, password: string): Promise<AuthUser> {
  return requestJson<AuthUser>(`${API_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
}

export function logout(): Promise<{ status: string }> {
  return requestJson<{ status: string }>(`${API_URL}/auth/logout`, { method: "POST" });
}

export function listUsers(): Promise<AuthUser[]> {
  return requestJson<AuthUser[]>(`${API_URL}/users`);
}

export function createUser(
  username: string,
  password: string,
  role: AuthUser["role"],
): Promise<AuthUser> {
  return requestJson<AuthUser>(`${API_URL}/users`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password, role }),
  });
}

export async function importXlsx(file: File): Promise<CsvImportResponse> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  const chunkSize = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
  }
  return requestJson<CsvImportResponse>(`${API_URL}/import/xlsx`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      filename: file.name,
      content_base64: btoa(binary),
    }),
  });
}
