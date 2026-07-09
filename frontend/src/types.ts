export type OptimizationMode = "auto" | "exact" | "advanced" | "fast";

export interface DemandInput {
  id: string;
  mark: string;
  diameter_mm: number;
  length_mm: number;
  quantity: number;
  phase: number;
}

export interface RemnantInput {
  rowId: string;
  id: string;
  diameter_mm: number;
  length_mm: number;
}

export interface CutOutput {
  mark: string;
  length_mm: number;
  phase: number;
}

export interface PatternOutput {
  stock_id: string;
  diameter_mm: number;
  stock_length_mm: number;
  source: "new" | "remnant";
  cuts: CutOutput[];
  remaining_mm: number;
  kerf_loss_mm: number;
}

export interface ReusableRemnantOutput {
  source_stock_id: string;
  diameter_mm: number;
  length_mm: number;
  source: "new" | "remnant";
  note: string;
}

export interface OptimizationResponse {
  run_id: string | null;
  requested_mode: OptimizationMode;
  solver_used: "exact" | "advanced" | "fast";
  summary: {
    piece_count: number;
    purchased_bar_count: number;
    demand_length_mm: number;
    purchased_length_mm: number;
    used_source_length_mm: number;
    new_stock_waste_mm: number;
    total_waste_mm: number;
    remnant_input_used_mm: number;
    remnant_source_used_mm: number;
    reusable_output_mm: number;
    scrap_output_mm: number;
    real_scrap_mm: number;
    kerf_loss_mm: number;
    new_stock_waste_rate: number;
    waste_rate: number;
    real_scrap_rate: number;
    purchase_waste_rate: number;
    demand_weight_kg: number;
    purchased_weight_kg: number;
    estimated_cost: number;
    estimated_carbon_kg: number;
    currency: string;
  };
  patterns: PatternOutput[];
  reusable_remnants: ReusableRemnantOutput[];
  comparison: {
    baseline_solver: string;
    optimized_solver: string;
    baseline_bar_count: number;
    optimized_bar_count: number;
    saved_bar_count: number;
    saved_weight_kg: number;
    saved_cost: number;
    saved_carbon_kg: number;
  } | null;
}

export interface Project {
  id: string;
  name: string;
  site: string;
  description: string;
  created_at: string;
  updated_at: string;
}

export interface ProjectSettings {
  project_id: string;
  stock_length_mm: number;
  min_reusable_mm: number;
  kerf_mm: number;
  steel_price_per_kg: number;
  carbon_kg_per_kg: number;
  currency: string;
  updated_at: string;
}

export interface InventoryItem {
  id: string;
  project_id: string;
  stock_code: string;
  diameter_mm: number;
  length_mm: number;
  steel_grade: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface InventoryMovement {
  id: string;
  project_id: string;
  stock_code: string;
  movement_type: string;
  diameter_mm: number;
  length_mm: number;
  run_id: string | null;
  details: Record<string, unknown>;
  created_at: string;
}

export interface RunSummary {
  id: string;
  project_id: string;
  requested_mode: string;
  solver_used: string;
  status: string;
  piece_count: number;
  purchased_bar_count: number;
  purchase_waste_rate: number;
  created_at: string;
}

export interface CommitResult {
  run_id: string;
  consumed_remnant_count: number;
  available_output_count: number;
  scrap_output_count: number;
}

export interface AuthUser {
  id: string;
  username: string;
  role: "admin" | "engineer" | "store" | "viewer";
  active: boolean;
  created_at: string;
}

export interface AuthStatus {
  setup_required: boolean;
  authenticated: boolean;
  user: AuthUser | null;
}

export interface CsvImportResponse {
  accepted_count: number;
  rejected_count: number;
  demands: Omit<DemandInput, "id">[];
  issues: { row: number; field: string; message: string }[];
}
