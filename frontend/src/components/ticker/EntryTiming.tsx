import { useApi } from "../../hooks/useApi";
import { scoreColor } from "../../lib/colors";

interface EntryTimingProps {
  ticker: string;
}

interface EntryData {
  ticker: string;
  current_price: number;
  entry_score: number;
  recommendation: string;
  signals: {
    rsi?: { score: number; rsi: number; signal: string };
    support?: { score: number; support_levels: Array<{ level: number; type: string; distance_pct: number }> };
    resistance?: { score: number; resistance_levels?: Array<{ level: number; type: string; distance_pct: number }> };
    volume?: { score: number; signal: string };
    ma_distance?: { score: number; distance_pct: number; signal: string };
  };
}

export default function EntryTiming({ ticker }: EntryTimingProps) {
  const { data, loading, error } = useApi<EntryData>(
    () => fetch(`/entry/${ticker}`).then(r => r.json()),
    [ticker]
  );

  if (loading) return <div className="p-4 text-text-secondary text-sm">Loading entry timing...</div>;
  if (error || !data) return <div className="p-4 text-text-secondary text-sm">Entry timing unavailable</div>;

  const score = data.entry_score ?? 0;
  const rsi = data.signals?.rsi?.rsi ?? 0;
  const rsiSignal = data.signals?.rsi?.signal ?? "—";
  const supportLevels = data.signals?.support?.support_levels ?? [];
  const resistanceLevels = data.signals?.resistance?.resistance_levels ?? [];
  const volumeSignal = data.signals?.volume?.signal ?? "—";
  const maDistance = data.signals?.ma_distance?.distance_pct ?? 0;

  return (
    <div className="p-4 grid grid-cols-3 gap-4">
      <div>
        <div className="text-[11px] text-text-muted uppercase tracking-wider mb-2">Entry Score</div>
        <div className="flex items-baseline gap-1.5">
          <span className={`text-3xl font-extrabold ${scoreColor(score)}`}>
            {(score / 10).toFixed(1)}
          </span>
          <span className="text-sm text-text-secondary">/ 10</span>
        </div>
        <div className="mt-2 h-1.5 rounded-full bg-border overflow-hidden">
          <div
            className="h-full rounded-full bg-gradient-to-r from-positive to-accent"
            style={{ width: `${score}%` }}
          />
        </div>
        <div className={`text-xs mt-1.5 ${scoreColor(score)}`}>
          {data.recommendation}
        </div>
      </div>

      <div>
        <div className="text-[11px] text-text-muted uppercase tracking-wider mb-2">Key Levels</div>
        <div className="flex flex-col gap-1.5">
          {resistanceLevels[0] && (
            <div className="flex justify-between text-[13px]">
              <span className="text-text-secondary">Resistance</span>
              <span className="text-danger font-semibold">${resistanceLevels[0].level.toFixed(2)}</span>
            </div>
          )}
          {supportLevels[0] && (
            <div className="flex justify-between text-[13px]">
              <span className="text-text-secondary">Support ({supportLevels[0].type})</span>
              <span className="text-positive font-semibold">${supportLevels[0].level.toFixed(2)}</span>
            </div>
          )}
          <div className="flex justify-between text-[13px]">
            <span className="text-text-secondary">RSI</span>
            <span className="text-text-primary font-semibold">{rsi.toFixed(1)}</span>
          </div>
          <div className="flex justify-between text-[13px]">
            <span className="text-text-secondary">Volume</span>
            <span className="text-text-primary font-semibold">{volumeSignal}</span>
          </div>
        </div>
      </div>

      <div>
        <div className="text-[11px] text-text-muted uppercase tracking-wider mb-2">Signals</div>
        <div className="flex flex-wrap gap-1.5">
          <span className="px-2.5 py-1 rounded-full bg-positive/10 border border-positive/20 text-positive text-[11px]">
            RSI: {rsiSignal}
          </span>
          <span className="px-2.5 py-1 rounded-full bg-accent/10 border border-accent/20 text-accent text-[11px]">
            MA dist: {maDistance.toFixed(1)}%
          </span>
        </div>
      </div>
    </div>
  );
}
