import { useApi } from "../../hooks/useApi";
import { api, type ClosedHolding, type ClosedStats } from "../../lib/api";
import { pnlColor } from "../../lib/colors";

export default function ClosedPositions() {
  const { data: stats } = useApi<ClosedStats>(() => api.closedStats());
  const { data: list } = useApi<{ closed: ClosedHolding[] }>(() => api.closedHoldings());

  if (!stats || stats.count === 0) {
    return (
      <div className="mt-8">
        <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-3">Closed Positions</h2>
        <div className="p-6 rounded-lg bg-surface border border-border text-sm text-text-secondary text-center">
          No closed positions yet. When you sell, record it via the trash button on a holding.
        </div>
      </div>
    );
  }

  return (
    <div className="mt-8">
      <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-3">
        Closed Positions <span className="text-text-muted/70 font-normal">({stats.count})</span>
      </h2>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
        <StatCard
          label="Realized P&L"
          value={`${stats.total_realized_pnl >= 0 ? "+" : ""}$${stats.total_realized_pnl.toLocaleString(undefined, { maximumFractionDigits: 2 })}`}
          valueClass={pnlColor(stats.total_realized_pnl)}
          sub={`${stats.count} trades`}
        />
        <StatCard
          label="Win Rate"
          value={stats.win_rate != null ? `${stats.win_rate.toFixed(1)}%` : "—"}
          sub="of closed trades"
        />
        <StatCard
          label="Avg Return"
          value={stats.avg_return_pct != null ? `${stats.avg_return_pct >= 0 ? "+" : ""}${stats.avg_return_pct.toFixed(2)}%` : "—"}
          valueClass={pnlColor(stats.avg_return_pct ?? 0)}
          sub="per trade"
        />
        <StatCard
          label="Avg Hold"
          value={stats.avg_hold_days != null ? `${stats.avg_hold_days.toFixed(0)}d` : "—"}
          sub="days per position"
        />
      </div>

      {(stats.best_trade || stats.worst_trade) && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
          {stats.best_trade && (
            <TradeCard label="Best Trade" trade={stats.best_trade} />
          )}
          {stats.worst_trade && (
            <TradeCard label="Worst Trade" trade={stats.worst_trade} />
          )}
        </div>
      )}

      {list?.closed && list.closed.length > 0 && (
        <div className="rounded-lg bg-surface border border-border overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-base/40">
                <th className="text-left px-3 py-2 text-[10px] font-semibold text-text-muted uppercase tracking-wider">Ticker</th>
                <th className="text-right px-3 py-2 text-[10px] font-semibold text-text-muted uppercase tracking-wider">Entry</th>
                <th className="text-right px-3 py-2 text-[10px] font-semibold text-text-muted uppercase tracking-wider">Exit</th>
                <th className="text-right px-3 py-2 text-[10px] font-semibold text-text-muted uppercase tracking-wider hidden sm:table-cell">Shares</th>
                <th className="text-right px-3 py-2 text-[10px] font-semibold text-text-muted uppercase tracking-wider hidden md:table-cell">Hold</th>
                <th className="text-right px-3 py-2 text-[10px] font-semibold text-text-muted uppercase tracking-wider">P&L</th>
                <th className="text-right px-3 py-2 text-[10px] font-semibold text-text-muted uppercase tracking-wider">%</th>
              </tr>
            </thead>
            <tbody>
              {[...list.closed]
                .sort((a, b) => (b.exit_date || "").localeCompare(a.exit_date || ""))
                .map((c, i) => (
                  <tr key={`${c.ticker}-${c.exit_date}-${i}`} className="border-b border-border-subtle last:border-0 hover:bg-base/30">
                    <td className="px-3 py-2 font-semibold text-text-primary">{c.ticker}</td>
                    <td className="px-3 py-2 text-right font-data text-text-secondary">
                      ${c.entry_price.toFixed(2)}
                      <div className="text-[10px] text-text-muted">{c.entry_date ?? "—"}</div>
                    </td>
                    <td className="px-3 py-2 text-right font-data text-text-secondary">
                      ${c.exit_price.toFixed(2)}
                      <div className="text-[10px] text-text-muted">{c.exit_date}</div>
                    </td>
                    <td className="px-3 py-2 text-right font-data text-text-muted hidden sm:table-cell">{c.shares.toFixed(2)}</td>
                    <td className="px-3 py-2 text-right font-data text-text-muted hidden md:table-cell">
                      {c.hold_days != null ? `${c.hold_days}d` : "—"}
                    </td>
                    <td className={`px-3 py-2 text-right font-data font-semibold ${pnlColor(c.realized_pnl)}`}>
                      {c.realized_pnl >= 0 ? "+" : ""}${c.realized_pnl.toFixed(2)}
                    </td>
                    <td className={`px-3 py-2 text-right font-data font-semibold ${pnlColor(c.realized_pnl_pct)}`}>
                      {c.realized_pnl_pct >= 0 ? "+" : ""}{c.realized_pnl_pct.toFixed(2)}%
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function StatCard({ label, value, valueClass, sub }: { label: string; value: string; valueClass?: string; sub?: string }) {
  return (
    <div className="p-3.5 rounded-lg bg-surface border border-border">
      <div className="text-[10px] font-semibold text-text-muted uppercase tracking-widest">{label}</div>
      <div className={`text-3xl font-bold mt-1 ${valueClass ?? "text-text-primary"}`}>{value}</div>
      {sub && <div className="text-[13px] text-text-secondary">{sub}</div>}
    </div>
  );
}

function TradeCard({ label, trade }: { label: string; trade: { ticker: string; pnl: number; pnl_pct: number } }) {
  return (
    <div className="p-4 rounded-lg bg-surface border border-border">
      <div className="text-[10px] font-semibold text-text-muted uppercase tracking-widest mb-2">{label}</div>
      <div className="text-lg font-bold text-text-primary">{trade.ticker}</div>
      <div className={`text-sm font-semibold ${pnlColor(trade.pnl_pct)}`}>
        {trade.pnl_pct >= 0 ? "+" : ""}{trade.pnl_pct.toFixed(2)}%
        <span className="ml-2 text-text-muted font-normal">
          ({trade.pnl >= 0 ? "+" : ""}${trade.pnl.toFixed(2)})
        </span>
      </div>
    </div>
  );
}
