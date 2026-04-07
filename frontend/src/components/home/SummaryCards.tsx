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
    <div className="grid grid-cols-4 gap-3 mb-5">
      <div className="p-3.5 rounded-2xl glass-card relative overflow-hidden">
        <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-accent/40 to-transparent" />
        <div className="text-[11px] text-text-muted uppercase tracking-wider">Portfolio Value</div>
        <div className="text-2xl font-bold text-text-primary mt-1 font-data">
          {risk ? `$${(risk.portfolio_value ?? 0).toLocaleString()}` : "—"}
        </div>
        {risk && (
          <div className={`text-[13px] font-data ${pnlColor(pnlDollar)} ${pnlDollar >= 0 ? "glow-positive" : "glow-danger"}`}>
            {pnlDollar >= 0 ? "+" : ""}${pnlDollar.toLocaleString()} ({pnlPct.toFixed(2)}%)
          </div>
        )}
      </div>
      <div className="p-3.5 rounded-2xl glass-card relative overflow-hidden">
        <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-accent/40 to-transparent" />
        <div className="text-[11px] text-text-muted uppercase tracking-wider">New Signals</div>
        <div className="text-2xl font-bold text-text-primary mt-1 font-data">{newSignals + sellSignals}</div>
        <div className="text-[13px] text-caution font-data">{newSignals} buy · {sellSignals} sell</div>
      </div>
      <div className="p-3.5 rounded-2xl glass-card relative overflow-hidden">
        <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-accent/40 to-transparent" />
        <div className="text-[11px] text-text-muted uppercase tracking-wider">Alerts</div>
        <div className="text-2xl font-bold text-text-primary mt-1 font-data">{alerts?.current.length ?? 0}</div>
        <div className="text-[13px] text-text-secondary truncate">
          {alerts?.current[0]?.message ?? "No active alerts"}
        </div>
      </div>
      <div className="p-3.5 rounded-2xl glass-card relative overflow-hidden">
        <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-accent/40 to-transparent" />
        <div className="text-[11px] text-text-muted uppercase tracking-wider">Win Rate</div>
        <div className="text-2xl font-bold text-text-primary mt-1 font-data">
          {accuracy ? `${accuracy.win_rate.toFixed(1)}%` : "—"}
        </div>
        <div className="text-[13px] text-text-secondary font-data">
          {accuracy ? `${accuracy.evaluated ?? 0}/${accuracy.total_signals ?? 0} picks` : ""}
        </div>
      </div>
    </div>
  );
}
