import type { Stock } from "../../lib/types";
import ScoreBadge from "../common/ScoreBadge";
import { scoreColor } from "../../lib/colors";

interface NewSignalsProps {
  stocks: Stock[];
  onTickerClick?: (ticker: string) => void;
}

export default function NewSignals({ stocks, onTickerClick }: NewSignalsProps) {
  const notable = stocks.filter(
    (s) => s.entry_signal === "STRONG_BUY" || s.entry_signal === "BUY" || s.sell_signal === "SELL" || s.sell_signal === "STRONG_SELL"
  ).slice(0, 5);

  return (
    <div className="rounded-lg bg-surface border border-border overflow-hidden">
      <div className="px-4 py-3 border-b border-border flex items-center justify-between">
        <span className="text-[10px] font-semibold text-text-muted uppercase tracking-widest">Top Signals</span>
        <span className="text-[10px] font-data text-text-muted">{notable.length}</span>
      </div>
      {notable.length === 0 ? (
        <div className="px-4 py-6 text-center text-sm text-text-muted">No active signals</div>
      ) : (
        notable.map((s) => (
          <div key={s.ticker} onClick={() => onTickerClick?.(s.ticker)} className="px-4 py-2.5 border-b border-border/40 last:border-0 flex justify-between items-center hover:bg-accent/[0.05] transition-colors cursor-pointer">
            <div className="flex items-center gap-3">
              <span className="text-[13px] font-semibold text-text-primary">{s.ticker}</span>
              <span className={`text-xs font-data font-medium ${scoreColor(s.composite_score ?? 0)}`}>{Math.round(s.composite_score ?? 0)}</span>
            </div>
            <ScoreBadge signal={s.entry_signal} />
          </div>
        ))
      )}
    </div>
  );
}
