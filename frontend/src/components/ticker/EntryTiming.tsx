import { useApi } from "../../hooks/useApi";
import { api } from "../../lib/api";
import type { EntryTiming as EntryTimingType } from "../../lib/types";
import { scoreColor } from "../../lib/colors";

interface EntryTimingProps {
  ticker: string;
}

export default function EntryTiming({ ticker }: EntryTimingProps) {
  const { data, loading } = useApi<EntryTimingType>(() => api.entry(ticker), [ticker]);

  if (loading) return <div className="p-4 text-text-secondary text-sm">Loading entry timing...</div>;
  if (!data) return <div className="p-4 text-text-secondary text-sm">Entry timing unavailable</div>;

  return (
    <div className="p-4 grid grid-cols-3 gap-4">
      <div>
        <div className="text-[11px] text-text-muted uppercase tracking-wider mb-2">Entry Score</div>
        <div className="flex items-baseline gap-1.5">
          <span className={`text-3xl font-extrabold ${scoreColor(data.timing_score)}`}>
            {(data.timing_score / 10).toFixed(1)}
          </span>
          <span className="text-sm text-text-secondary">/ 10</span>
        </div>
        <div className="mt-2 h-1.5 rounded-full bg-border overflow-hidden">
          <div
            className="h-full rounded-full bg-gradient-to-r from-positive to-accent"
            style={{ width: `${data.timing_score}%` }}
          />
        </div>
        <div className={`text-xs mt-1.5 ${scoreColor(data.timing_score)}`}>
          {data.recommendation}
        </div>
      </div>

      <div>
        <div className="text-[11px] text-text-muted uppercase tracking-wider mb-2">Key Levels</div>
        <div className="flex flex-col gap-1.5">
          {data.resistance_levels[0] && (
            <div className="flex justify-between text-[13px]">
              <span className="text-text-secondary">Resistance</span>
              <span className="text-danger font-semibold">${data.resistance_levels[0].toFixed(2)}</span>
            </div>
          )}
          {data.support_levels[0] && (
            <div className="flex justify-between text-[13px]">
              <span className="text-text-secondary">Support</span>
              <span className="text-positive font-semibold">${data.support_levels[0].toFixed(2)}</span>
            </div>
          )}
          <div className="flex justify-between text-[13px]">
            <span className="text-text-secondary">RSI</span>
            <span className="text-text-primary font-semibold">{data.rsi.toFixed(1)}</span>
          </div>
          <div className="flex justify-between text-[13px]">
            <span className="text-text-secondary">Volume</span>
            <span className="text-text-primary font-semibold">{data.volume_signal}</span>
          </div>
        </div>
      </div>

      <div>
        <div className="text-[11px] text-text-muted uppercase tracking-wider mb-2">Signals</div>
        <div className="flex flex-wrap gap-1.5">
          <span className="px-2.5 py-1 rounded-full bg-positive/10 border border-positive/20 text-positive text-[11px]">
            RSI: {data.rsi_signal}
          </span>
          <span className="px-2.5 py-1 rounded-full bg-accent/10 border border-accent/20 text-accent text-[11px]">
            MA dist: {data.ma_distance_pct.toFixed(1)}%
          </span>
        </div>
      </div>
    </div>
  );
}
