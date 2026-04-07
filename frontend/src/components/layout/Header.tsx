import { useState, useCallback } from "react";
import type { ScanResult } from "../../lib/types";
import { api } from "../../lib/api";

interface HeaderProps {
  scan: ScanResult | null;
  onScanComplete?: () => void;
}

export default function Header({ scan, onScanComplete }: HeaderProps) {
  const regime = scan?.market_regime;
  const [scanning, setScanning] = useState(false);
  const [scanMsg, setScanMsg] = useState<string | null>(null);

  const regimeColor = {
    bull: "bg-positive/15 text-positive",
    bear: "bg-danger/15 text-danger",
    sideways: "bg-caution/15 text-caution",
  }[regime?.regime ?? "sideways"] ?? "bg-text-secondary/15 text-text-secondary";

  const pollStatus = useCallback(() => {
    const interval = setInterval(async () => {
      try {
        const status = await api.scanStatus();
        if (!status.running) {
          clearInterval(interval);
          setScanning(false);
          if (status.error) {
            setScanMsg(`Scan failed: ${status.error}`);
          } else {
            setScanMsg("Scan complete");
            onScanComplete?.();
          }
          setTimeout(() => setScanMsg(null), 3000);
        }
      } catch {
        clearInterval(interval);
        setScanning(false);
      }
    }, 3000);
    return interval;
  }, [onScanComplete]);

  async function runScan() {
    if (scanning) return;
    setScanning(true);
    setScanMsg("Scanning...");
    try {
      await fetch("/scan", { headers: { "X-API-Key": "stock-picker" } });
      pollStatus();
    } catch {
      setScanning(false);
      setScanMsg("Failed to start scan");
      setTimeout(() => setScanMsg(null), 3000);
    }
  }

  return (
    <header className="flex items-center justify-between px-6 py-3 border-b border-border bg-surface">
      <div className="flex items-center gap-3">
        <div className="text-sm text-text-secondary">
          {scan ? (
            <>Last scan: {new Date(scan.timestamp).toLocaleTimeString()}</>
          ) : (
            "No scan data"
          )}
        </div>
        {scanMsg && (
          <span className={`text-xs font-medium ${scanning ? "text-accent" : "text-positive"}`}>
            {scanning && <span className="inline-block w-1.5 h-1.5 rounded-full bg-accent animate-pulse-dot mr-1.5" />}
            {scanMsg}
          </span>
        )}
      </div>
      <div className="flex items-center gap-3">
        {regime && (
          <>
            <span className={`px-3 py-1 rounded-md text-xs font-semibold ${regimeColor}`}>
              Regime: {regime.regime.charAt(0).toUpperCase() + regime.regime.slice(1)}
            </span>
            <span className="text-xs text-text-muted font-data">
              SPY ${regime.spy_price.toFixed(2)}
            </span>
            <span className="text-xs text-text-muted font-data">
              VIX {regime.macro.vix.current.toFixed(1)}
            </span>
          </>
        )}
        <button
          onClick={runScan}
          disabled={scanning}
          className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-all ${
            scanning
              ? "bg-accent/20 text-accent cursor-wait"
              : "bg-accent text-white hover:bg-accent/90"
          }`}
        >
          {scanning ? "Scanning..." : "Run Scan"}
        </button>
      </div>
    </header>
  );
}
