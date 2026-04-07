import { useApi } from "../../hooks/useApi";
import { scoreColor } from "../../lib/colors";

interface SignalDetail {
  score: number;
  details?: Record<string, unknown>;
}

interface MomentumData {
  ticker: string;
  composite_score?: number;
  signal?: string;
  signals?: Record<string, SignalDetail>;
}

const SIGNAL_LABELS: Record<string, string> = {
  analyst_revision: "Analyst Revisions",
  insider_buying: "Insider Buying",
  revenue_acceleration: "Revenue Acceleration",
  institutional_validation: "Institutional Validation",
  earnings_surprise: "Earnings Surprise",
};

const SIGNAL_COLOR: Record<string, string> = {
  STRONG_MOMENTUM: "text-positive",
  MOMENTUM: "text-positive",
  NEUTRAL: "text-caution",
  WEAK: "text-danger",
};

export default function MomentumTab({ ticker }: { ticker: string }) {
  const { data, loading, error } = useApi<MomentumData>(
    () => fetch(`/momentum/${ticker}`).then(r => r.json()),
    [ticker]
  );
  if (loading) return <div className="p-4 text-text-secondary text-sm">Loading momentum...</div>;
  if (error || !data) return <div className="p-4 text-text-secondary text-sm">Momentum data unavailable</div>;

  const signals = Object.entries(data.signals ?? {});

  return (
    <div className="p-4">
      <div className="flex items-center gap-3 mb-4">
        <span className={`text-2xl font-bold ${scoreColor((data.composite_score ?? 0) * 10)}`}>
          {data.composite_score?.toFixed(1) ?? "—"}
        </span>
        <span className="text-sm text-text-secondary">/ 10</span>
        <span className={`px-2.5 py-1 rounded-md text-xs font-bold ${SIGNAL_COLOR[data.signal ?? ""] ?? "text-text-secondary"} bg-surface`}>
          {data.signal ?? "—"}
        </span>
      </div>

      <div className="space-y-2">
        {signals.map(([key, sig]) => (
          <div key={key} className="p-3 rounded-lg bg-base border border-border">
            <div className="flex justify-between items-center mb-1">
              <span className="text-xs font-semibold text-text-primary">
                {SIGNAL_LABELS[key] ?? key}
              </span>
              <span className={`text-sm font-bold ${scoreColor(sig.score * 50)}`}>
                {sig.score.toFixed(1)}
              </span>
            </div>
            <div className="h-1.5 rounded-full bg-border overflow-hidden">
              <div
                className="h-full rounded-full bg-gradient-to-r from-accent to-positive"
                style={{ width: `${Math.min(sig.score * 50, 100)}%` }}
              />
            </div>
            {sig.details && (
              <div className="flex flex-wrap gap-x-4 gap-y-0.5 mt-1.5">
                {Object.entries(sig.details).slice(0, 3).map(([dk, dv]) => (
                  <span key={dk} className="text-[11px] text-text-muted">
                    {dk.replace(/_/g, " ")}: <span className="text-text-secondary">
                      {typeof dv === "number" ? dv.toFixed(1) : String(dv)}
                    </span>
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
