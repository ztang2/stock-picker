import { useApi } from "../hooks/useApi";
import { api } from "../lib/api";
import type { AccuracyResponse } from "../lib/types";
import { pnlColor } from "../lib/colors";

export default function Accuracy() {
  const { data, loading } = useApi<AccuracyResponse>(() => api.accuracy());
  if (loading) return <div className="text-text-secondary">Loading accuracy...</div>;
  if (!data) return <div className="text-text-secondary">No accuracy data</div>;

  return (
    <div>
      <h1 className="text-xl font-bold mb-4">Accuracy</h1>
      <div className="grid grid-cols-4 gap-3 mb-6">
        <div className="p-3.5 rounded-xl bg-surface border border-border">
          <div className="text-[11px] text-text-muted uppercase tracking-wider">Win Rate</div>
          <div className="text-3xl font-bold text-text-primary mt-1">{data.win_rate?.toFixed(1) ?? "—"}%</div>
          <div className="text-[13px] text-text-secondary">{data.evaluated ?? 0}/{data.total_signals ?? 0} picks</div>
        </div>
        <div className="p-3.5 rounded-xl bg-surface border border-border">
          <div className="text-[11px] text-text-muted uppercase tracking-wider">Avg Return</div>
          <div className={`text-3xl font-bold mt-1 ${pnlColor(data.avg_return ?? 0)}`}>
            {data.avg_return != null ? `${data.avg_return.toFixed(2)}%` : "—"}
          </div>
          <div className="text-[13px] text-text-secondary">per pick</div>
        </div>
        <div className="p-3.5 rounded-xl bg-surface border border-border">
          <div className="text-[11px] text-text-muted uppercase tracking-wider">Avg Alpha</div>
          <div className={`text-3xl font-bold mt-1 ${pnlColor(data.avg_alpha ?? 0)}`}>
            {data.avg_alpha != null ? `${data.avg_alpha.toFixed(2)}%` : "—"}
          </div>
          <div className="text-[13px] text-text-secondary">vs SPY</div>
        </div>
        <div className="p-3.5 rounded-xl bg-surface border border-border">
          <div className="text-[11px] text-text-muted uppercase tracking-wider">Buy Signals</div>
          <div className="text-3xl font-bold text-text-primary mt-1">{data.buy_signals ?? "—"}</div>
          <div className="text-[13px] text-text-secondary">of {data.total_signals ?? 0} total</div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        {data.best_pick && (
          <div className="p-4 rounded-xl bg-surface border border-border">
            <div className="text-[11px] text-text-muted uppercase tracking-wider mb-2">Best Pick</div>
            <div className="text-lg font-bold text-text-primary">{data.best_pick.ticker}</div>
            <div className={`text-sm font-semibold ${pnlColor(data.best_pick.return_pct)}`}>
              +{data.best_pick.return_pct?.toFixed(2) ?? "—"}% return
            </div>
            <div className="text-xs text-text-secondary">
              +{data.best_pick.alpha_pct?.toFixed(2) ?? "—"}% alpha
            </div>
          </div>
        )}
        {data.worst_pick && (
          <div className="p-4 rounded-xl bg-surface border border-border">
            <div className="text-[11px] text-text-muted uppercase tracking-wider mb-2">Worst Pick</div>
            <div className="text-lg font-bold text-text-primary">{data.worst_pick.ticker}</div>
            <div className={`text-sm font-semibold ${pnlColor(data.worst_pick.return_pct)}`}>
              {data.worst_pick.return_pct?.toFixed(2) ?? "—"}% return
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
