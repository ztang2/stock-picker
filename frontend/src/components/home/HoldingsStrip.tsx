import type { StopLossAlert } from "../../lib/types";
import { pnlColor } from "../../lib/colors";

interface HoldingsStripProps {
  alerts: StopLossAlert[];
  onTickerClick: (ticker: string) => void;
}

export default function HoldingsStrip({ alerts, onTickerClick }: HoldingsStripProps) {
  if (alerts.length === 0) return null;

  const sorted = [...alerts].sort(
    (a, b) => b.shares * b.current_price - a.shares * a.current_price
  );

  const biggestMoverIdx = sorted.reduce((maxIdx, alert, idx, arr) =>
    Math.abs(alert.pnl_pct) > Math.abs(arr[maxIdx].pnl_pct) ? idx : maxIdx, 0
  );

  return (
    <div className="mb-4">
      <div className="text-[10px] text-text-muted uppercase tracking-widest mb-2">Holdings</div>
      <div className="flex gap-3 overflow-x-auto pb-1 scrollbar-hide">
        {sorted.map((alert, idx) => {
          const isBiggestMover = idx === biggestMoverIdx;
          const pnlBarWidth = Math.min(Math.abs(alert.pnl_pct) * 4, 100);

          return (
            <div
              key={alert.ticker}
              onClick={() => onTickerClick(alert.ticker)}
              className={`flex-shrink-0 w-[120px] bg-surface border rounded-lg p-3 hover:border-accent/30 transition-all cursor-pointer ${
                isBiggestMover ? "border-accent/40" : "border-border"
              }`}
            >
              <div className="font-bold text-[13px] text-text-primary tracking-tight">{alert.ticker}</div>
              <div className="font-data text-[12px] text-text-secondary mt-0.5">
                ${alert.current_price.toFixed(2)}
              </div>
              <div className={`font-data text-[12px] font-medium mt-1 ${pnlColor(alert.pnl_pct)}`}>
                {alert.pnl_pct > 0 ? "+" : ""}{alert.pnl_pct.toFixed(1)}%
              </div>
              {/* P&L progress bar */}
              <div className="mt-2 h-[3px] bg-border rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${alert.pnl_pct >= 0 ? "bg-positive" : "bg-danger"}`}
                  style={{ width: `${pnlBarWidth}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
