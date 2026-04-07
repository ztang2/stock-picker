import type { Stock } from "../../lib/types";
import ScoreBadge from "../common/ScoreBadge";

interface NewSignalsProps {
  stocks: Stock[];
}

export default function NewSignals({ stocks }: NewSignalsProps) {
  const notable = stocks.filter(
    (s) => s.entry_signal === "STRONG_BUY" || s.entry_signal === "BUY" || s.sell_signal === "SELL" || s.sell_signal === "STRONG_SELL"
  ).slice(0, 5);

  return (
    <div className="rounded-xl bg-surface border border-border overflow-hidden">
      <div className="px-4 py-3 border-b border-border text-xs font-bold text-text-primary uppercase tracking-wider">
        Top Signals
      </div>
      {notable.map((s) => (
        <div key={s.ticker} className="px-4 py-2.5 border-b border-border/50 last:border-0 flex justify-between items-center">
          <div>
            <span className="text-[13px] font-semibold text-text-primary">{s.ticker}</span>
            <span className="text-xs text-text-muted ml-1.5">{s.sector}</span>
          </div>
          <ScoreBadge signal={s.entry_signal} />
        </div>
      ))}
    </div>
  );
}
