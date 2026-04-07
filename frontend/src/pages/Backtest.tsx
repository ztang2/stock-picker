import { useApi } from "../hooks/useApi";
import { api } from "../lib/api";
import type { BacktestResult } from "../lib/types";
import { pnlColor } from "../lib/colors";

export default function Backtest() {
  const { data, loading } = useApi<BacktestResult>(() => api.backtest());
  if (loading) return <div className="text-text-secondary">Loading backtest...</div>;
  if (!data) return <div className="text-text-secondary">No backtest data</div>;

  return (
    <div>
      <h1 className="text-xl font-bold mb-4">Backtest</h1>
      <div className="grid grid-cols-4 gap-3 mb-6">
        <div className="p-3.5 rounded-xl bg-surface border border-border">
          <div className="text-[11px] text-text-muted uppercase tracking-wider">Total Return</div>
          <div className={`text-2xl font-bold mt-1 ${pnlColor(data.summary.total_return)}`}>
            {(data.summary.total_return * 100).toFixed(1)}%
          </div>
        </div>
        <div className="p-3.5 rounded-xl bg-surface border border-border">
          <div className="text-[11px] text-text-muted uppercase tracking-wider">Win Rate</div>
          <div className="text-2xl font-bold text-text-primary mt-1">{(data.summary.win_rate * 100).toFixed(0)}%</div>
        </div>
        <div className="p-3.5 rounded-xl bg-surface border border-border">
          <div className="text-[11px] text-text-muted uppercase tracking-wider">Sharpe Ratio</div>
          <div className="text-2xl font-bold text-text-primary mt-1">{data.summary.sharpe_ratio.toFixed(2)}</div>
        </div>
        <div className="p-3.5 rounded-xl bg-surface border border-border">
          <div className="text-[11px] text-text-muted uppercase tracking-wider">Avg Win / Loss</div>
          <div className="text-2xl font-bold text-text-primary mt-1">
            {(data.summary.avg_win * 100).toFixed(1)}% / {(data.summary.avg_loss * 100).toFixed(1)}%
          </div>
        </div>
      </div>
      <div className="rounded-xl border border-border overflow-hidden">
        <table className="w-full">
          <thead className="bg-surface">
            <tr>
              <th className="py-2.5 px-3 text-left text-[11px] text-text-muted uppercase">Month</th>
              <th className="py-2.5 px-3 text-left text-[11px] text-text-muted uppercase">Avg Return</th>
              <th className="py-2.5 px-3 text-left text-[11px] text-text-muted uppercase">Best</th>
              <th className="py-2.5 px-3 text-left text-[11px] text-text-muted uppercase">Worst</th>
              <th className="py-2.5 px-3 text-left text-[11px] text-text-muted uppercase">Drawdown</th>
            </tr>
          </thead>
          <tbody>
            {data.backtest_results.map((r) => (
              <tr key={r.month} className="border-t border-surface">
                <td className="py-2.5 px-3 text-sm text-text-primary">{r.month}</td>
                <td className={`py-2.5 px-3 text-sm font-semibold ${pnlColor(r.avg_return)}`}>
                  {(r.avg_return * 100).toFixed(1)}%
                </td>
                <td className="py-2.5 px-3 text-sm text-positive">{r.best_stock} +{(r.best_return * 100).toFixed(1)}%</td>
                <td className="py-2.5 px-3 text-sm text-danger">{(r.worst_return * 100).toFixed(1)}%</td>
                <td className="py-2.5 px-3 text-sm text-danger">{(r.drawdown * 100).toFixed(1)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
