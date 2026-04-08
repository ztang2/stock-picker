import { useScan } from "../App";
import ScoreBadge from "../components/common/ScoreBadge";
import RadarChart from "../components/common/RadarChart";

export default function Momentum() {
  const { scan, loading } = useScan();
  if (loading || !scan) return <div className="text-text-secondary">Loading...</div>;

  const top = scan.top.slice(0, 20);

  return (
    <div>
      <h1 className="text-xl font-bold mb-4">Momentum Radar</h1>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {top.map((s) => (
          <div key={s.ticker} className="p-4 rounded-lg bg-surface border border-border flex items-center gap-4">
            <RadarChart
              scores={{ fund: s.fundamentals_pct, val: s.valuation_pct, tech: s.technicals_pct, risk: s.risk_pct, grow: s.growth_pct }}
              size={64}
              showLabels={false}
            />
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                <span className="font-bold text-text-primary">{s.ticker}</span>
                <ScoreBadge signal={s.entry_signal} />
              </div>
              <div className="text-xs text-text-secondary">{s.name} · {s.sector}</div>
              <div className="text-xs text-text-muted mt-1">Score: {s.composite_score?.toFixed(1) ?? "—"} · RSI: {s.rsi?.toFixed(1) ?? "—"}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
