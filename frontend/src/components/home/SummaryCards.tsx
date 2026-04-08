import type { ScanResult, AlertsResponse, AccuracyResponse, RiskSummary } from "../../lib/types";
import { pnlColor } from "../../lib/colors";

interface SummaryCardsProps {
  scan: ScanResult;
  alerts: AlertsResponse | null;
  accuracy: AccuracyResponse | null;
  risk: RiskSummary | null;
}

export default function SummaryCards({ scan, alerts, accuracy, risk }: SummaryCardsProps) {
  const newSignals = scan.top.filter((s) => s.entry_signal === "STRONG_BUY" || s.entry_signal === "BUY").length;
  const sellSignals = scan.top.filter((s) => s.sell_signal === "SELL" || s.sell_signal === "STRONG_SELL").length;

  const pnlDollar = risk?.total_pnl ?? 0;
  const pnlPct = risk?.total_pnl_pct ?? 0;

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5">
      {/* Portfolio Value — hero card */}
      <div className="p-4 rounded-lg bg-surface border border-border relative overflow-hidden group hover:border-accent/30 transition-colors">
        <div className="absolute top-0 left-0 w-full h-[2px] bg-gradient-to-r from-accent/60 via-accent/20 to-transparent" />
        <div className="text-[10px] text-text-muted uppercase tracking-widest font-medium">Portfolio</div>
        <div className="text-2xl font-bold text-text-primary mt-1.5 font-data tracking-tight">
          {risk ? `$${(risk.portfolio_value ?? 0).toLocaleString()}` : "—"}
        </div>
        {risk && (
          <div className={`text-xs font-data font-medium mt-0.5 ${pnlColor(pnlDollar)}`}>
            {pnlDollar >= 0 ? "+" : ""}${pnlDollar.toLocaleString()}
            <span className="text-text-muted ml-1">({pnlPct.toFixed(2)}%)</span>
          </div>
        )}
      </div>

      {/* Signals */}
      <div className="p-4 rounded-lg bg-surface border border-border relative overflow-hidden hover:border-accent/30 transition-colors">
        <div className="text-[10px] text-text-muted uppercase tracking-widest font-medium">Signals</div>
        <div className="text-2xl font-bold text-text-primary mt-1.5 font-data tracking-tight">{newSignals + sellSignals}</div>
        <div className="flex gap-2 mt-0.5">
          {newSignals > 0 && <span className="text-xs font-data text-positive font-medium">{newSignals} buy</span>}
          {sellSignals > 0 && <span className="text-xs font-data text-danger font-medium">{sellSignals} sell</span>}
          {newSignals === 0 && sellSignals === 0 && <span className="text-xs text-text-muted">No signals</span>}
        </div>
      </div>

      {/* Alerts */}
      <div className="p-4 rounded-lg bg-surface border border-border relative overflow-hidden hover:border-accent/30 transition-colors">
        {(alerts?.current.length ?? 0) > 0 && (
          <div className="absolute top-3 right-3 w-2 h-2 rounded-full bg-danger animate-pulse-dot" />
        )}
        <div className="text-[10px] text-text-muted uppercase tracking-widest font-medium">Alerts</div>
        <div className="text-2xl font-bold text-text-primary mt-1.5 font-data tracking-tight">{alerts?.current.length ?? 0}</div>
        <div className="text-xs text-text-muted truncate mt-0.5">
          {alerts?.current[0]?.message ?? "All clear"}
        </div>
      </div>

      {/* Win Rate */}
      <div className="p-4 rounded-lg bg-surface border border-border relative overflow-hidden hover:border-accent/30 transition-colors">
        <div className="text-[10px] text-text-muted uppercase tracking-widest font-medium">Win Rate</div>
        <div className="text-2xl font-bold text-text-primary mt-1.5 font-data tracking-tight">
          {accuracy ? `${accuracy.win_rate?.toFixed(1) ?? "—"}%` : "—"}
        </div>
        <div className="text-xs text-text-muted font-data mt-0.5">
          {accuracy ? `${accuracy.evaluated ?? 0}/${accuracy.total_signals ?? 0} evaluated` : ""}
        </div>
      </div>
    </div>
  );
}
