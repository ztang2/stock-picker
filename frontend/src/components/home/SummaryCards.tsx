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

  return (
    <div className="grid grid-cols-4 gap-3 mb-5">
      <div className="p-3.5 rounded-xl bg-surface border border-border">
        <div className="text-[11px] text-text-muted uppercase tracking-wider">Portfolio Value</div>
        <div className="text-2xl font-bold text-text-primary mt-1">
          {risk ? `$${risk.total_portfolio_value.toLocaleString()}` : "—"}
        </div>
        {risk && (
          <div className={`text-[13px] ${pnlColor(risk.total_pnl)}`}>
            {risk.total_pnl >= 0 ? "+" : ""}${risk.total_pnl.toLocaleString()} ({risk.total_pnl_pct.toFixed(2)}%)
          </div>
        )}
      </div>
      <div className="p-3.5 rounded-xl bg-surface border border-border">
        <div className="text-[11px] text-text-muted uppercase tracking-wider">New Signals</div>
        <div className="text-2xl font-bold text-text-primary mt-1">{newSignals + sellSignals}</div>
        <div className="text-[13px] text-caution">{newSignals} buy · {sellSignals} sell</div>
      </div>
      <div className="p-3.5 rounded-xl bg-surface border border-border">
        <div className="text-[11px] text-text-muted uppercase tracking-wider">Alerts</div>
        <div className="text-2xl font-bold text-text-primary mt-1">{alerts?.current.length ?? 0}</div>
        <div className="text-[13px] text-text-secondary truncate">
          {alerts?.current[0]?.message ?? "No active alerts"}
        </div>
      </div>
      <div className="p-3.5 rounded-xl bg-surface border border-border">
        <div className="text-[11px] text-text-muted uppercase tracking-wider">Win Rate</div>
        <div className="text-2xl font-bold text-text-primary mt-1">
          {accuracy ? `${accuracy.accuracy_pct.toFixed(1)}%` : "—"}
        </div>
        <div className="text-[13px] text-text-secondary">
          {accuracy ? `${accuracy.correct}/${accuracy.total_predictions} picks` : ""}
        </div>
      </div>
    </div>
  );
}
