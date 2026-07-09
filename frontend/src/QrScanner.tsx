import { useEffect, useRef, useState } from "react";
import { getInventoryItem, transitionInventoryItem } from "./api";
import type { InventoryItem } from "./types";

type BarcodeResult = { rawValue: string };
type BarcodeDetectorInstance = { detect(source: HTMLVideoElement): Promise<BarcodeResult[]> };
type BarcodeDetectorConstructor = new (options: { formats: string[] }) => BarcodeDetectorInstance;

interface Props {
  projectId: string;
  onClose(): void;
  onUpdated(): Promise<void>;
}

export default function QrScanner({ projectId, onClose, onUpdated }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [manual, setManual] = useState("");
  const [item, setItem] = useState<InventoryItem | null>(null);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [cameraAvailable, setCameraAvailable] = useState(true);

  const resolvePayload = async (raw: string) => {
    try {
      const payload = JSON.parse(raw) as {
        type?: string;
        project_id?: string;
        item_id?: string;
      };
      if (
        payload.type !== "rebarflow-remnant" ||
        payload.project_id !== projectId ||
        !payload.item_id
      ) {
        throw new Error("Bu QR kod aktif DonatıPlan projesine ait değil.");
      }
      setItem(await getInventoryItem(projectId, payload.item_id));
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "QR kod okunamadı.");
    }
  };

  useEffect(() => {
    let stream: MediaStream | null = null;
    let animation = 0;
    let stopped = false;
    let lastRead = 0;
    const Detector = (window as unknown as { BarcodeDetector?: BarcodeDetectorConstructor })
      .BarcodeDetector;

    if (!Detector || !navigator.mediaDevices?.getUserMedia) {
      setCameraAvailable(false);
      return undefined;
    }

    const detector = new Detector({ formats: ["qr_code"] });
    const scan = async (timestamp: number) => {
      if (stopped) return;
      const video = videoRef.current;
      if (video && video.readyState >= 2 && timestamp - lastRead > 350) {
        lastRead = timestamp;
        try {
          const results = await detector.detect(video);
          if (results[0]?.rawValue) {
            await resolvePayload(results[0].rawValue);
            return;
          }
        } catch {
          // A transient frame error should not stop the scanner.
        }
      }
      animation = requestAnimationFrame(scan);
    };

    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: false })
      .then((mediaStream) => {
        stream = mediaStream;
        if (videoRef.current) {
          videoRef.current.srcObject = mediaStream;
          void videoRef.current.play();
        }
        animation = requestAnimationFrame(scan);
      })
      .catch(() => setCameraAvailable(false));

    return () => {
      stopped = true;
      cancelAnimationFrame(animation);
      stream?.getTracks().forEach((track) => track.stop());
    };
  }, [projectId]);

  const transition = async (
    status: "available" | "reserved" | "consumed" | "scrap",
  ) => {
    if (!item) return;
    setBusy(true);
    setError("");
    try {
      setItem(await transitionInventoryItem(projectId, item.id, status, note));
      await onUpdated();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Stok hareketi uygulanamadı.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="scanner-backdrop" role="dialog" aria-modal="true">
      <div className="scanner-card">
        <div className="scanner-heading">
          <div><span>QR</span><h2>Artık parça işlemi</h2></div>
          <button onClick={onClose}>×</button>
        </div>
        {cameraAvailable ? (
          <video ref={videoRef} className="scanner-video" playsInline muted />
        ) : (
          <div className="scanner-fallback">Kamera/BarcodeDetector kullanılamıyor. QR içeriğini aşağıya yapıştırın.</div>
        )}
        <div className="scanner-manual">
          <input value={manual} onChange={(event) => setManual(event.target.value)} placeholder="QR JSON içeriği" />
          <button onClick={() => resolvePayload(manual)}>Kodu çöz</button>
        </div>
        {error && <div className="error-box">{error}</div>}
        {item && (
          <div className="scanned-item">
            <strong>{item.stock_code}</strong>
            <span>Ø{item.diameter_mm} · {item.length_mm} mm · {item.steel_grade}</span>
            <em>{item.status}</em>
            <input value={note} onChange={(event) => setNote(event.target.value)} placeholder="İşlem notu (isteğe bağlı)" />
            <div>
              {item.status === "reserved" && <button disabled={busy} onClick={() => transition("available")}>Rezerveyi kaldır</button>}
              {item.status === "available" && <button disabled={busy} onClick={() => transition("reserved")}>Rezerve et</button>}
              {(item.status === "available" || item.status === "reserved") && <button disabled={busy} onClick={() => transition("consumed")}>Tüket</button>}
              {(item.status === "available" || item.status === "reserved") && <button className="danger" disabled={busy} onClick={() => transition("scrap")}>Hurda</button>}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
