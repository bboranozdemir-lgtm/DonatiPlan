import { useEffect, useMemo, useState, type KeyboardEvent } from "react";
import {
  bbsTemplateUrl,
  bootstrapAdmin,
  createProject,
  commitRun,
  createUser,
  importCsv,
  importXlsx,
  getAuthStatus,
  inventoryLabelsUrl,
  listProjects,
  listRuns,
  listUsers,
  loadProjectDemands,
  loadInventory,
  loadMovements,
  loadProjectSettings,
  login,
  logout,
  optimizeProject,
  readCsvFile,
  projectBackupUrl,
  reportUrl,
  saveInventory,
  saveProjectDemands,
  saveProjectSettings,
  restoreProjectBackup,
} from "./api";
import type {
  DemandInput,
  OptimizationMode,
  OptimizationResponse,
  Project,
  ProjectSettings,
  RemnantInput,
  RunSummary,
  InventoryMovement,
  AuthStatus,
  AuthUser,
} from "./types";
import QrScanner from "./QrScanner";

const uid = () => crypto.randomUUID();

const initialDemands: DemandInput[] = [
  { id: uid(), mark: "K1-ALT", diameter_mm: 16, length_mm: 4200, quantity: 6, phase: 1 },
  { id: uid(), mark: "K1-ÜST", diameter_mm: 16, length_mm: 3600, quantity: 4, phase: 1 },
  { id: uid(), mark: "K2", diameter_mm: 12, length_mm: 2750, quantity: 8, phase: 2 },
];

const initialRemnants: RemnantInput[] = [];
const defaultSettings: ProjectSettings = {
  project_id: "",
  stock_length_mm: 12000,
  min_reusable_mm: 1000,
  kerf_mm: 0,
  steel_price_per_kg: 0,
  carbon_kg_per_kg: 0,
  currency: "TRY",
  updated_at: "",
};

function number(value: string): number {
  return Number.parseInt(value, 10) || 0;
}

function metres(value: number): string {
  return `${(value / 1000).toLocaleString("tr-TR", { maximumFractionDigits: 2 })} m`;
}

function percentOrNoNewStock(rate: number, purchasedLengthMm: number): string {
  return purchasedLengthMm > 0
    ? `%${(rate * 100).toFixed(1)}`
    : "Yeni stok kullanılmadı";
}

function money(value: number, currency: string): string {
  return new Intl.NumberFormat("tr-TR", {
    style: "currency",
    currency: currency || "TRY",
    maximumFractionDigits: 0,
  }).format(value);
}

function shortDate(value: string): string {
  return new Intl.DateTimeFormat("tr-TR", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function solverName(value: string): string {
  if (value === "exact") return "Kesin çözüm";
  if (value === "advanced") return "Gelişmiş CP-SAT";
  return "Hızlı çözüm";
}

function App() {
  const [demands, setDemands] = useState(initialDemands);
  const [remnants, setRemnants] = useState(initialRemnants);
  const [mode, setMode] = useState<OptimizationMode>("auto");
  const [result, setResult] = useState<OptimizationResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [importNote, setImportNote] = useState("");
  const [demandBusy, setDemandBusy] = useState(false);
  const [demandNote, setDemandNote] = useState("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProjectId, setActiveProjectId] = useState("");
  const [newProjectName, setNewProjectName] = useState("");
  const [newProjectSite, setNewProjectSite] = useState("");
  const [projectBusy, setProjectBusy] = useState(false);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [commitBusy, setCommitBusy] = useState(false);
  const [commitNote, setCommitNote] = useState("");
  const [settings, setSettings] = useState<ProjectSettings>(defaultSettings);
  const [settingsBusy, setSettingsBusy] = useState(false);
  const [settingsNote, setSettingsNote] = useState("");
  const [inventoryBusy, setInventoryBusy] = useState(false);
  const [inventoryNote, setInventoryNote] = useState("");
  const [movements, setMovements] = useState<InventoryMovement[]>([]);
  const [auth, setAuth] = useState<AuthStatus | null>(null);
  const [authUsername, setAuthUsername] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authBusy, setAuthBusy] = useState(false);
  const [authError, setAuthError] = useState("");
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [newUsername, setNewUsername] = useState("");
  const [newUserPassword, setNewUserPassword] = useState("");
  const [newUserRole, setNewUserRole] = useState<AuthUser["role"]>("engineer");
  const [userNote, setUserNote] = useState("");
  const [scannerOpen, setScannerOpen] = useState(false);

  useEffect(() => {
    getAuthStatus()
      .then(setAuth)
      .catch((reason) => setAuthError(
        reason instanceof Error ? reason.message : "Oturum durumu alınamadı.",
      ));
  }, []);

  useEffect(() => {
    if (!auth?.authenticated) return;
    let cancelled = false;
    listProjects()
      .then((items) => {
        if (cancelled) return;
        setProjects(items);
        const remembered = localStorage.getItem("rebarflow.activeProject");
        const selected = items.find((item) => item.id === remembered)?.id ?? items[0]?.id ?? "";
        setActiveProjectId(selected);
      })
      .catch((reason) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Projeler yüklenemedi.");
      });
    return () => { cancelled = true; };
  }, [auth?.authenticated]);

  useEffect(() => {
    if (auth?.user?.role !== "admin") {
      setUsers([]);
      return;
    }
    listUsers().then(setUsers).catch(() => setUsers([]));
  }, [auth?.user?.role]);

  useEffect(() => {
    if (!activeProjectId) {
      setRemnants([]);
      setRuns([]);
      setSettings(defaultSettings);
      setMovements([]);
      return;
    }
    let cancelled = false;
    localStorage.setItem("rebarflow.activeProject", activeProjectId);
    Promise.all([
      loadProjectDemands(activeProjectId),
      loadInventory(activeProjectId),
      listRuns(activeProjectId),
      loadProjectSettings(activeProjectId),
      loadMovements(activeProjectId),
    ])
      .then(([savedDemands, inventory, history, loadedSettings, loadedMovements]) => {
        if (cancelled) return;
        setDemands(savedDemands.map((item) => ({ id: uid(), ...item })));
        setRemnants(inventory.map((item) => ({
          rowId: item.id,
          id: item.stock_code,
          diameter_mm: item.diameter_mm,
          length_mm: item.length_mm,
        })));
        setRuns(history);
        setSettings(loadedSettings);
        setMovements(loadedMovements);
        setResult(null);
        setCommitNote("");
        setSettingsNote("");
        setInventoryNote("");
        setDemandNote("");
      })
      .catch((reason) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Proje verileri yüklenemedi.");
      });
    return () => { cancelled = true; };
  }, [activeProjectId]);

  const totalPieces = useMemo(
    () => demands.reduce((sum, item) => sum + item.quantity, 0),
    [demands],
  );
  const role = auth?.user?.role;
  const canPlan = role === "admin" || role === "engineer";
  const canManageInventory = canPlan || role === "store";

  const updateDemand = (id: string, field: keyof DemandInput, value: string) => {
    setDemands((rows) =>
      rows.map((row) =>
        row.id === id ? { ...row, [field]: field === "mark" ? value : number(value) } : row,
      ),
    );
  };

  const updateRemnant = (rowId: string, field: keyof RemnantInput, value: string) => {
    setRemnants((rows) =>
      rows.map((row) =>
        row.rowId === rowId
          ? { ...row, [field]: field === "id" ? value : number(value) }
          : row,
      ),
    );
  };

  const runOptimization = async () => {
    if (!activeProjectId) {
      setError("Optimizasyonu kaydetmek için önce bir proje oluşturun.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await saveProjectDemands(activeProjectId, demands);
      await saveInventory(activeProjectId, remnants);
      setResult(await optimizeProject(activeProjectId, demands, remnants, mode));
      setRuns(await listRuns(activeProjectId));
      setMovements(await loadMovements(activeProjectId));
      setCommitNote("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Beklenmeyen bir hata oluştu.");
    } finally {
      setBusy(false);
    }
  };

  const handleSaveDemands = async () => {
    if (!activeProjectId || !canPlan) return;
    setDemandBusy(true);
    setDemandNote("");
    setError("");
    try {
      const saved = await saveProjectDemands(activeProjectId, demands);
      setDemands(saved.map((item) => ({ id: uid(), ...item })));
      setDemandNote("Talepler projeye kaydedildi.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Talepler kaydedilemedi.");
    } finally {
      setDemandBusy(false);
    }
  };

  const handleCommit = async () => {
    if (!activeProjectId || !result?.run_id) return;
    setCommitBusy(true);
    setError("");
    try {
      const committed = await commitRun(activeProjectId, result.run_id);
      const inventory = await loadInventory(activeProjectId);
      setRemnants(inventory.map((item) => ({
        rowId: item.id,
        id: item.stock_code,
        diameter_mm: item.diameter_mm,
        length_mm: item.length_mm,
      })));
      setRuns(await listRuns(activeProjectId));
      setMovements(await loadMovements(activeProjectId));
      setCommitNote(
        `${committed.consumed_remnant_count} parça tüketildi, ` +
        `${committed.available_output_count} kullanılabilir artık stoğa eklendi.`,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Plan stoğa işlenemedi.");
    } finally {
      setCommitBusy(false);
    }
  };

  const handleSaveInventory = async () => {
    if (!activeProjectId || !canManageInventory) return;
    setInventoryBusy(true);
    setInventoryNote("");
    setError("");
    try {
      const inventory = await saveInventory(activeProjectId, remnants);
      setRemnants(inventory.map((item) => ({
        rowId: item.id,
        id: item.stock_code,
        diameter_mm: item.diameter_mm,
        length_mm: item.length_mm,
      })));
      setMovements(await loadMovements(activeProjectId));
      setInventoryNote("Stok kaydedildi.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Stok kaydedilemedi.");
    } finally {
      setInventoryBusy(false);
    }
  };

  const handleCreateProject = async () => {
    if (newProjectName.trim().length < 2) {
      setError("Proje adı en az 2 karakter olmalı.");
      return;
    }
    setProjectBusy(true);
    setError("");
    try {
      const created = await createProject(newProjectName.trim(), newProjectSite.trim());
      setProjects((items) => [created, ...items]);
      setNewProjectName("");
      setNewProjectSite("");
      setActiveProjectId(created.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Proje oluşturulamadı.");
    } finally {
      setProjectBusy(false);
    }
  };

  const handleAuthenticate = async () => {
    setAuthBusy(true);
    setAuthError("");
    try {
      if (auth?.setup_required) {
        await bootstrapAdmin(authUsername.trim(), authPassword);
      } else {
        await login(authUsername.trim(), authPassword);
      }
      setAuth(await getAuthStatus());
      setAuthPassword("");
    } catch (err) {
      setAuthError(err instanceof Error ? err.message : "Oturum açılamadı.");
    } finally {
      setAuthBusy(false);
    }
  };

  const submitAuthForm = () => {
    if (!authBusy && authUsername.length >= 3 && authPassword.length >= 10) {
      void handleAuthenticate();
    }
  };

  const handleAuthEnter = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      event.preventDefault();
      submitAuthForm();
    }
  };

  const handleLogout = async () => {
    await logout();
    setProjects([]);
    setActiveProjectId("");
    setAuth(await getAuthStatus());
  };

  const handleCreateUser = async () => {
    setUserNote("");
    setError("");
    try {
      await createUser(newUsername.trim(), newUserPassword, newUserRole);
      setUsers(await listUsers());
      setNewUsername("");
      setNewUserPassword("");
      setUserNote("Kullanıcı oluşturuldu.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Kullanıcı oluşturulamadı.");
    }
  };

  const handleRestoreBackup = async (file: File | undefined) => {
    if (!file) return;
    setProjectBusy(true);
    setError("");
    try {
      const restored = await restoreProjectBackup(file);
      setProjects((items) => [restored, ...items]);
      setActiveProjectId(restored.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Yedek geri yüklenemedi.");
    } finally {
      setProjectBusy(false);
    }
  };

  const updateSetting = (field: keyof ProjectSettings, value: string) => {
    setSettings((current) => ({
      ...current,
      [field]: field === "currency" ? value.toUpperCase() : Number(value) || 0,
    }));
  };

  const handleSaveSettings = async () => {
    if (!activeProjectId) return;
    setSettingsBusy(true);
    setSettingsNote("");
    setError("");
    try {
      const saved = await saveProjectSettings(activeProjectId, {
        stock_length_mm: settings.stock_length_mm,
        min_reusable_mm: settings.min_reusable_mm,
        kerf_mm: settings.kerf_mm,
        steel_price_per_kg: settings.steel_price_per_kg,
        carbon_kg_per_kg: settings.carbon_kg_per_kg,
        currency: settings.currency,
      });
      setSettings(saved);
      setSettingsNote("Mühendislik ayarları kaydedildi.");
      setResult(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ayarlar kaydedilemedi.");
    } finally {
      setSettingsBusy(false);
    }
  };

  const handleImportFile = async (file: File | undefined) => {
    if (!file) return;
    setError("");
    setImportNote("");
    try {
      const imported = file.name.toLowerCase().endsWith(".xlsx")
        ? await importXlsx(file)
        : await importCsv(await readCsvFile(file));
      setDemands(imported.demands.map((item) => ({ ...item, id: uid() })));
      setResult(null);
      setImportNote(
        `${imported.accepted_count} satır alındı` +
        (imported.rejected_count ? `, ${imported.rejected_count} satır hatalı olduğu için atlandı.` : "."),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "BBS dosyası okunamadı.");
    }
  };

  const refreshInventoryAndMovements = async () => {
    if (!activeProjectId) return;
    const [inventory, loadedMovements] = await Promise.all([
      loadInventory(activeProjectId),
      loadMovements(activeProjectId),
    ]);
    setRemnants(inventory.map((entry) => ({
      rowId: entry.id,
      id: entry.stock_code,
      diameter_mm: entry.diameter_mm,
      length_mm: entry.length_mm,
    })));
    setMovements(loadedMovements);
  };

  if (!auth || auth.setup_required || !auth.authenticated) {
    return (
      <div className="auth-shell">
        <form
          className="auth-card"
          onSubmit={(event) => {
            event.preventDefault();
            submitAuthForm();
          }}
        >
          <div className="brand-mark">DP</div>
          <p className="eyebrow">DONATIPLAN / GÜVENLİ ÇALIŞMA ALANI</p>
          <h1>{auth?.setup_required ? "İlk yöneticiyi oluştur." : "Tekrar hoş geldin."}</h1>
          <p>
            {auth?.setup_required
              ? "En az 10 karakterli bir parola belirleyin. Bu hesap kullanıcıları ve yedekleri yönetecek."
              : "Projelerinize erişmek için kullanıcı bilgilerinizle giriş yapın."}
          </p>
          <label>Kullanıcı adı<input value={authUsername} onChange={(event) => setAuthUsername(event.target.value)} onKeyDown={handleAuthEnter} autoComplete="username" /></label>
          <label>Parola<input type="password" value={authPassword} onChange={(event) => setAuthPassword(event.target.value)} onKeyDown={handleAuthEnter} autoComplete={auth?.setup_required ? "new-password" : "current-password"} /></label>
          {authError && <div className="error-box">{authError}</div>}
          <button type="submit" disabled={authBusy || authUsername.length < 3 || authPassword.length < 10}>
            {authBusy ? "Kontrol ediliyor…" : auth?.setup_required ? "Yönetici hesabını oluştur" : "Giriş yap"}
          </button>
        </form>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-mark" aria-hidden="true">DP</div>
        <div>
          <strong>DonatıPlan</strong>
          <span>Akıllı Donatı Kesim, Artık ve Hurda Analizi · by BBO</span>
        </div>
        <div className="user-status">
          <span>{auth.user?.username} · {auth.user?.role}</span>
          <button onClick={handleLogout}>Çıkış</button>
        </div>
        <div className="status"><i /> {activeProjectId ? "Veritabanına bağlı" : "Proje bekleniyor"}</div>
      </header>

      <main>
        <section className="project-toolbar">
          <div className="project-selector">
            <label>Aktif proje</label>
            <select value={activeProjectId} onChange={(event) => setActiveProjectId(event.target.value)}>
              <option value="">Proje seçin</option>
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}{project.site ? ` · ${project.site}` : ""}
                </option>
              ))}
            </select>
          </div>
          <div className="new-project-form">
            <input
              placeholder="Yeni proje adı"
              value={newProjectName}
              disabled={!canPlan}
              onChange={(event) => setNewProjectName(event.target.value)}
            />
            <input
              placeholder="Şantiye / şehir"
              value={newProjectSite}
              disabled={!canPlan}
              onChange={(event) => setNewProjectSite(event.target.value)}
            />
            <button disabled={projectBusy || !canPlan} onClick={handleCreateProject}>
              {projectBusy ? "Oluşturuluyor…" : "+ Proje oluştur"}
            </button>
            {activeProjectId && (
              <a className="toolbar-link" href={projectBackupUrl(activeProjectId)}>Yedek al</a>
            )}
            {role === "admin" && (
              <label className="toolbar-link file-button">
                Yedek yükle
                <input type="file" accept=".json,application/json" onChange={(event) => handleRestoreBackup(event.target.files?.[0])} />
              </label>
            )}
          </div>
        </section>
        {!canPlan && (
          <div className="permission-note">
            {role === "store"
              ? "Depo rolü: QR ve stok hareketleri açık; proje ve optimizasyon alanları salt okunur."
              : "Görüntüleyici rolü: proje verileri ve raporlar salt okunur."}
          </div>
        )}
        {activeProjectId && (
          <details className="settings-panel">
            <summary>Proje mühendislik ayarları</summary>
            <div className="settings-grid">
              <label>Standart çubuk (mm)<input disabled={!canPlan} type="number" value={settings.stock_length_mm} onChange={(event) => updateSetting("stock_length_mm", event.target.value)} /></label>
              <label>Min. artık (mm)<input disabled={!canPlan} type="number" value={settings.min_reusable_mm} onChange={(event) => updateSetting("min_reusable_mm", event.target.value)} /></label>
              <label>Kesim kaybı (mm)<input disabled={!canPlan} type="number" value={settings.kerf_mm} onChange={(event) => updateSetting("kerf_mm", event.target.value)} /></label>
              <label>Çelik fiyatı / kg<input disabled={!canPlan} type="number" step="0.01" value={settings.steel_price_per_kg} onChange={(event) => updateSetting("steel_price_per_kg", event.target.value)} /></label>
              <label>Karbon kgCO₂e / kg<input disabled={!canPlan} type="number" step="0.01" value={settings.carbon_kg_per_kg} onChange={(event) => updateSetting("carbon_kg_per_kg", event.target.value)} /></label>
              <label>Para birimi<input disabled={!canPlan} maxLength={3} value={settings.currency} onChange={(event) => updateSetting("currency", event.target.value)} /></label>
              <button disabled={settingsBusy || !canPlan} onClick={handleSaveSettings}>{settingsBusy ? "Kaydediliyor…" : "Ayarları kaydet"}</button>
              {settingsNote && <span>{settingsNote}</span>}
            </div>
          </details>
        )}
        {auth.user?.role === "admin" && (
          <details className="settings-panel users-panel">
            <summary>Kullanıcılar ve roller</summary>
            <div className="user-management">
              <div className="user-list">
                {users.map((user) => <span key={user.id}>{user.username}<em>{user.role}</em></span>)}
              </div>
              <input placeholder="Kullanıcı adı" value={newUsername} onChange={(event) => setNewUsername(event.target.value)} />
              <input type="password" placeholder="En az 10 karakter parola" value={newUserPassword} onChange={(event) => setNewUserPassword(event.target.value)} />
              <select value={newUserRole} onChange={(event) => setNewUserRole(event.target.value as AuthUser["role"])}>
                <option value="engineer">Mühendis</option>
                <option value="store">Depo sorumlusu</option>
                <option value="viewer">Görüntüleyici</option>
                <option value="admin">Yönetici</option>
              </select>
              <button disabled={newUsername.length < 3 || newUserPassword.length < 10} onClick={handleCreateUser}>Kullanıcı ekle</button>
              {userNote && <small>{userNote}</small>}
            </div>
          </details>
        )}
        <section className="hero">
          <div>
            <p className="eyebrow">AKILLI DONATI KESİM VE FİRE ANALİZİ / by BBO</p>
            <h1>DonatıPlan<br />Akıllı Donatı Kesim, Artık ve Hurda Analizi</h1>
            <p className="hero-copy">
              Donatı taleplerini ve sahadaki artık parçaları tek planda birleştir.
              Sonucu çubuk bazında izle, karşılaştır ve uygula.
            </p>
          </div>
          <div className="hero-stat">
            <span>Planlanan parça</span>
            <strong>{totalPieces}</strong>
            <small>{demands.length} poz · {remnants.length} artık parça</small>
          </div>
        </section>

        <section className="workspace-grid">
          <div className="panel input-panel">
            <div className="panel-heading">
              <div><span>01</span><h2>Donatı talepleri</h2></div>
              <div className="heading-actions">
                <a className="template-link" href={bbsTemplateUrl}>Şablon indir</a>
                {canPlan && <label className="text-button file-button">
                  CSV / Excel yükle
                  <input type="file" accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={(event) => handleImportFile(event.target.files?.[0])} />
                </label>}
                <button className="text-button" disabled={!canPlan || !activeProjectId || demandBusy} onClick={handleSaveDemands}>
                  {demandBusy ? "Kaydediliyor…" : "Talepleri kaydet"}
                </button>
                <button className="text-button" disabled={!canPlan} onClick={() => setDemands((rows) => [
                  ...rows,
                  { id: uid(), mark: `P${rows.length + 1}`, diameter_mm: 16, length_mm: 3000, quantity: 1, phase: 1 },
                ])}>+ Satır ekle</button>
              </div>
            </div>
            {importNote && <div className="import-note">{importNote}</div>}
            {demandNote && <div className="import-note">{demandNote}</div>}
            <div className="table-wrap">
              <table>
                <thead><tr><th>Poz</th><th>Ø mm</th><th>Boy mm</th><th>Adet</th><th>Faz</th><th /></tr></thead>
                <tbody>
                  {demands.map((row) => (
                    <tr key={row.id}>
                      <td><input disabled={!canPlan} value={row.mark} onChange={(e) => updateDemand(row.id, "mark", e.target.value)} /></td>
                      <td><input disabled={!canPlan} type="number" value={row.diameter_mm} onChange={(e) => updateDemand(row.id, "diameter_mm", e.target.value)} /></td>
                      <td><input disabled={!canPlan} type="number" value={row.length_mm} onChange={(e) => updateDemand(row.id, "length_mm", e.target.value)} /></td>
                      <td><input disabled={!canPlan} type="number" value={row.quantity} onChange={(e) => updateDemand(row.id, "quantity", e.target.value)} /></td>
                      <td><input disabled={!canPlan} type="number" value={row.phase} onChange={(e) => updateDemand(row.id, "phase", e.target.value)} /></td>
                      <td><button disabled={!canPlan} className="icon-button" aria-label="Satırı sil" onClick={() => setDemands((rows) => rows.filter((item) => item.id !== row.id))}>×</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="panel-heading subheading">
              <div><span>02</span><h2>Artık parça envanteri</h2></div>
              <div className="heading-actions">
                {activeProjectId && <a className="template-link" href={inventoryLabelsUrl(activeProjectId)}>QR etiketleri</a>}
                {activeProjectId && canManageInventory && <button className="text-button qr-button" onClick={() => setScannerOpen(true)}>QR okut</button>}
                <button className="text-button" disabled={!canManageInventory || !activeProjectId || inventoryBusy} onClick={handleSaveInventory}>
                  {inventoryBusy ? "Kaydediliyor…" : "Stoğu kaydet"}
                </button>
                <button className="text-button" disabled={!canManageInventory} onClick={() => setRemnants((rows) => [
                  ...rows,
                  { rowId: uid(), id: `ART-${rows.length + 1}`, diameter_mm: 16, length_mm: 2500 },
                ])}>+ Artık ekle</button>
              </div>
            </div>
            <div className="table-wrap">
              <table>
                <thead><tr><th>Stok kodu</th><th>Ø mm</th><th>Boy mm</th><th /></tr></thead>
                <tbody>
                  {remnants.map((row) => (
                    <tr key={row.rowId}>
                      <td><input disabled={!canManageInventory} value={row.id} onChange={(e) => updateRemnant(row.rowId, "id", e.target.value)} /></td>
                      <td><input disabled={!canManageInventory} type="number" value={row.diameter_mm} onChange={(e) => updateRemnant(row.rowId, "diameter_mm", e.target.value)} /></td>
                      <td><input disabled={!canManageInventory} type="number" value={row.length_mm} onChange={(e) => updateRemnant(row.rowId, "length_mm", e.target.value)} /></td>
                      <td><button disabled={!canManageInventory} className="icon-button" aria-label="Artığı sil" onClick={() => setRemnants((rows) => rows.filter((item) => item.rowId !== row.rowId))}>×</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {inventoryNote && <div className="import-note">{inventoryNote}</div>}

            <div className="action-row">
              <label>
                Çözüm modu
                <select disabled={!canPlan} value={mode} onChange={(e) => setMode(e.target.value as OptimizationMode)}>
                  <option value="auto">Otomatik</option>
                  <option value="exact">Kesin çözüm</option>
                  <option value="advanced">Gelişmiş CP-SAT</option>
                  <option value="fast">Hızlı çözüm</option>
                </select>
              </label>
              <button className="primary-button" disabled={!canPlan || busy || demands.length === 0 || !activeProjectId} onClick={runOptimization}>
                {busy ? "Hesaplanıyor…" : "Planı optimize et"}
              </button>
            </div>
            {error && <div className="error-box" role="alert">{error}</div>}
          </div>

          <aside className="panel result-panel">
            <div className="panel-heading">
              <div><span>03</span><h2>Optimizasyon sonucu</h2></div>
              {result && <em>{solverName(result.solver_used)}</em>}
            </div>
            {!result ? (
              <div className="empty-state">
                <div className="empty-bars"><i /><i /><i /></div>
                <h3>Plan henüz oluşturulmadı</h3>
                <p>Verileri kontrol edip optimizasyonu başlat.</p>
              </div>
            ) : (
              <>
                <div className="summary-grid">
                  <article><span>Yeni çubuk</span><strong>{result.summary.purchased_bar_count}</strong></article>
                  <article><span>Satın alınan</span><strong>{metres(result.summary.purchased_length_mm)}</strong></article>
                  <article><span>Kullanılan kaynak</span><strong>{metres(result.summary.used_source_length_mm)}</strong></article>
                  <article><span>Toplam ihtiyaç</span><strong>{metres(result.summary.demand_length_mm)}</strong></article>
                  <article><span>Yeni stok artığı</span><strong>{metres(result.summary.new_stock_waste_mm)}</strong></article>
                  <article><span>Yeni stok artık oranı</span><strong>{percentOrNoNewStock(result.summary.new_stock_waste_rate, result.summary.purchased_length_mm)}</strong></article>
                  <article><span>Toplam artık</span><strong>{metres(result.summary.total_waste_mm)}</strong></article>
                  <article className="accent"><span>İşlem toplam artık oranı</span><strong>%{(result.summary.waste_rate * 100).toFixed(1)}</strong></article>
                  <article><span>Gerçek hurda</span><strong>{metres(result.summary.real_scrap_mm)}</strong></article>
                  <article><span>Gerçek hurda oranı</span><strong>%{(result.summary.real_scrap_rate * 100).toFixed(1)}</strong></article>
                  <article><span>Kullanılabilir artık</span><strong>{metres(result.summary.reusable_output_mm)}</strong></article>
                  <article><span>Artıktan kullanılan</span><strong>{metres(result.summary.remnant_input_used_mm)}</strong></article>
                  <article><span>Tahmini maliyet</span><strong>{money(result.summary.estimated_cost, result.summary.currency)}</strong></article>
                </div>
                {result.comparison && (
                  <div className="savings-card">
                    <div><span>Kurtarılan çubuk</span><strong>{result.comparison.saved_bar_count}</strong></div>
                    <div><span>Kurtarılan çelik</span><strong>{result.comparison.saved_weight_kg.toFixed(1)} kg</strong></div>
                    <div><span>Maliyet tasarrufu</span><strong>{money(result.comparison.saved_cost, result.summary.currency)}</strong></div>
                    <div><span>Karbon tasarrufu</span><strong>{result.comparison.saved_carbon_kg.toFixed(1)} kgCO₂e</strong></div>
                  </div>
                )}
                {(result.reusable_remnants ?? []).length > 0 && (
                  <div className="reusable-list">
                    <h3>Kullanılabilir artıklar</h3>
                    {(result.reusable_remnants ?? []).map((item, index) => (
                      <div key={`${item.source_stock_id}-${index}`}>
                        <strong>Ø{item.diameter_mm} · {item.length_mm} mm</strong>
                        <span>{item.note}</span>
                      </div>
                    ))}
                  </div>
                )}
                <div className="patterns">
                  <h3>Kesim şeması <small>{result.patterns.length} çubuk</small></h3>
                  {result.patterns.map((pattern) => (
                    <article className="pattern" key={pattern.stock_id}>
                      <div className="pattern-meta">
                        <strong>{pattern.stock_id}</strong>
                        <span>Ø{pattern.diameter_mm} · {metres(pattern.stock_length_mm)}</span>
                        <em className={pattern.source}>{pattern.source === "new" ? "Yeni" : "Artık"}</em>
                      </div>
                      <div className="bar" aria-label={`${pattern.stock_id} kesim planı`}>
                        {pattern.cuts.map((cut, index) => (
                          <div
                            className="cut"
                            key={`${cut.mark}-${index}`}
                            style={{ width: `${(cut.length_mm / pattern.stock_length_mm) * 100}%` }}
                            title={`${cut.mark}: ${cut.length_mm} mm`}
                          ><span>{cut.mark}</span><small>{cut.length_mm}</small></div>
                        ))}
                        {pattern.remaining_mm > 0 && (
                          <div
                            className="remainder"
                            style={{ width: `${(pattern.remaining_mm / pattern.stock_length_mm) * 100}%` }}
                            title={
                              pattern.remaining_mm >= settings.min_reusable_mm
                                ? `Kalan: ${pattern.remaining_mm} mm · Bu parça bu projede kullanılmadı, stokta tekrar kullanılabilir.`
                                : `Kalan: ${pattern.remaining_mm} mm · Gerçek hurda`
                            }
                          />
                        )}
                      </div>
                    </article>
                  ))}
                </div>
                {result.run_id && (
                  <div className="result-actions">
                    <div className="commit-card">
                      <div>
                        <strong>Plan kaydedildi · {result.run_id.slice(0, 8)}</strong>
                        <span>Fiziksel kesim yapıldıktan sonra stok hareketlerini onaylayın.</span>
                      </div>
                      <button disabled={!canManageInventory || commitBusy || Boolean(commitNote)} onClick={handleCommit}>
                        {commitBusy ? "İşleniyor…" : commitNote ? "Stoğa işlendi" : "Planı stoğa işle"}
                      </button>
                    </div>
                    <div className="download-actions">
                      <a href={reportUrl(activeProjectId, result.run_id, "xlsx")}>Excel raporu</a>
                      <a href={reportUrl(activeProjectId, result.run_id, "pdf")}>PDF kesim planı</a>
                    </div>
                  </div>
                )}
                {commitNote && <div className="commit-note">{commitNote}</div>}
              </>
            )}
            {runs.length > 0 && (
              <div className="history">
                <h3>Son çalışmalar</h3>
                {runs.slice(0, 5).map((run) => (
                  <div className="history-row" key={run.id}>
                    <div>
                      <strong>{solverName(run.solver_used)}</strong>
                      <span>{shortDate(run.created_at)} · {run.piece_count} parça</span>
                    </div>
                    <div className="history-actions">
                      <em>%{(run.purchase_waste_rate * 100).toFixed(1)}</em>
                      <a href={reportUrl(activeProjectId, run.id, "pdf")}>PDF</a>
                      <a href={reportUrl(activeProjectId, run.id, "xlsx")}>XLSX</a>
                    </div>
                  </div>
                ))}
              </div>
            )}
            {movements.length > 0 && (
              <div className="history movements">
                <h3>Stok hareketleri</h3>
                {movements.slice(0, 8).map((movement) => (
                  <div className="history-row" key={movement.id}>
                    <div>
                      <strong>{movement.stock_code}</strong>
                      <span>
                        {movement.movement_type} · Ø{movement.diameter_mm} · {movement.length_mm} mm
                        {typeof movement.details.actor === "string" ? ` · ${movement.details.actor}` : ""}
                      </span>
                    </div>
                    <em>{shortDate(movement.created_at)}</em>
                  </div>
                ))}
              </div>
            )}
          </aside>
        </section>
      </main>
      {scannerOpen && activeProjectId && canManageInventory && (
        <QrScanner
          projectId={activeProjectId}
          onClose={() => setScannerOpen(false)}
          onUpdated={refreshInventoryAndMovements}
        />
      )}
      <footer>DonatıPlan · Yerel karar destek sistemi · Geliştiren: Berke Boran Özdemir · Mühendis onayının yerine geçmez</footer>
    </div>
  );
}

export default App;
