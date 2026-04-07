import { useApi } from "../hooks/useApi";
import { api } from "../lib/api";
import type { BacktestResult } from "../lib/types";
import { pnlColor } from "../lib/colors";

const PCT_LABELS: Record<string, string> = { "1m": "1 Month", "3m": "3 Months", "6m": "6 Months" };

export default function Backtest() {
  const { data, loading } = useApi<BacktestResult>(() => api.backtest());
  if (loading) return <div className="text-text-secondary">Loading backtest...</div>;
  if (!data) return <div className="text-text-secondary">No backtest data</div>;

  const periods = Object.entries(data.periods ?? {});

  return (
    <div>
      <h1 className="text-xl font-bold mb-1">Backtest</h1>
      <div className="text-[13px] text-text-secondary mb-4">
        {data.months_back ?? "—"} months back · Top picks: {data.top_picks?.join(", ") ?? "—"}
      </div>

      <div className="grid grid-cols-3 gap-3 mb-6">
        {periods.map(([key, p]) => (
          <div key={key} className="p-3.5 rounded-xl bg-surface border border-border">
            <div className="text-[11px] text-text-muted uppercase tracking-wider mb-2">{PCT_LABELS[key] ?? key}</div>
            <div className="grid grid-cols-2 gap-y-1.5 text-sm">
              <span className="text-text-secondary">Pick return</span>
              <span className={`font-semibold text-right ${pnlColor(p.pick_return)}`}>
                {p.pick_return != null ? `${(p.pick_return * 100).toFixed(1)}%` : "—"}
              </span>
              <span className="text-text-secondary">SPY return</span>
              <span className={`font-semibold text-right ${pnlColor(p.spy_return)}`}>
                {p.spy_return != null ? `${(p.spy_return * 100).toFixed(1)}%` : "—"}
              </span>
              <span className="text-text-secondary">Alpha</span>
              <span className={`font-semibold text-right ${pnlColor(p.alpha)}`}>
                {p.alpha != null ? `${(p.alpha * 100).toFixed(1)}%` : "—"}
              </span>
              <span className="text-text-secondary">Win rate</span>
              <span className="font-semibold text-right text-text-primary">
                {p.win_rate != null ? `${(p.win_rate * 100).toFixed(0)}%` : "—"}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
