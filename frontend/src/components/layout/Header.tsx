import type { ScanResult } from "../../lib/types";

interface HeaderProps {
  scan: ScanResult | null;
}

export default function Header({ scan }: HeaderProps) {
  const regime = scan?.market_regime;

  const regimeColor = {
    bull: "bg-positive/15 text-positive",
    bear: "bg-danger/15 text-danger",
    sideways: "bg-caution/15 text-caution",
  }[regime?.regime ?? "sideways"] ?? "bg-text-secondary/15 text-text-secondary";

  return (
    <header className="flex items-center justify-between px-6 py-3 border-b border-border bg-surface">
      <div className="text-sm text-text-secondary">
        {scan ? (
          <>Last scan: {new Date(scan.timestamp).toLocaleTimeString()}</>
        ) : (
          "No scan data"
        )}
      </div>
      <div className="flex items-center gap-3">
        {regime && (
          <>
            <span className={`px-3 py-1 rounded-md text-xs font-semibold ${regimeColor}`}>
              Regime: {regime.regime.charAt(0).toUpperCase() + regime.regime.slice(1)}
            </span>
            <span className="text-xs text-text-muted">
              SPY ${regime.spy_price.toFixed(2)}
            </span>
            <span className="text-xs text-text-muted">
              VIX {regime.macro.vix.current.toFixed(1)}
            </span>
          </>
        )}
      </div>
    </header>
  );
}
