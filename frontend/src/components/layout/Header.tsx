import { useState, useCallback } from "react";
import type { ScanResult } from "../../lib/types";
import { api } from "../../lib/api";
import { useTheme } from "../../hooks/useTheme";

interface HeaderProps {
  scan: ScanResult | null;
  onScanComplete?: () => void;
}

export default function Header({ scan, onScanComplete }: HeaderProps) {
  const regime = scan?.market_regime;
  const [scanning, setScanning] = useState(false);
  const [scanMsg, setScanMsg] = useState<string | null>(null);
  const { theme, toggle } = useTheme();

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
              {regime.regime.charAt(0).toUpperCase() + regime.regime.slice(1)}
            </span>
            <span className="text-xs text-text-muted font-data">
              SPY ${regime.spy_price?.toFixed(2) ?? "—"}
            </span>
            <span className="text-xs text-text-muted font-data">
              VIX {regime.macro?.vix?.current?.toFixed(1) ?? "—"}
            </span>
          </>
        )}

        {/* Theme toggle */}
        <button
          onClick={toggle}
          className="w-8 h-8 rounded-lg bg-surface-raised flex items-center justify-center text-text-muted hover:text-text-primary hover:bg-border/50 transition-colors"
          title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
        >
          {theme === "dark" ? (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
            </svg>
          ) : (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
            </svg>
          )}
        </button>

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
