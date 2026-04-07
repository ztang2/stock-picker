import { useApi } from "../hooks/useApi";
import { api } from "../lib/api";
import type { AccuracyResponse } from "../lib/types";

export default function Accuracy() {
  const { data, loading } = useApi<AccuracyResponse>(() => api.accuracy());
  if (loading) return <div className="text-text-secondary">Loading accuracy...</div>;
  if (!data) return <div className="text-text-secondary">No accuracy data</div>;

  return (
    <div>
      <h1 className="text-xl font-bold mb-4">Accuracy</h1>
      <div className="grid grid-cols-3 gap-3 mb-6">
        <div className="p-3.5 rounded-xl bg-surface border border-border">
          <div className="text-[11px] text-text-muted uppercase tracking-wider">Overall Accuracy</div>
          <div className="text-3xl font-bold text-text-primary mt-1">{data.accuracy_pct.toFixed(1)}%</div>
          <div className="text-[13px] text-text-secondary">{data.correct}/{data.total_predictions} picks</div>
        </div>
        {Object.entries(data.by_signal).map(([signal, stats]) => (
          <div key={signal} className="p-3.5 rounded-xl bg-surface border border-border">
            <div className="text-[11px] text-text-muted uppercase tracking-wider">{signal}</div>
            <div className="text-2xl font-bold text-text-primary mt-1">{stats.accuracy.toFixed(1)}%</div>
            <div className="text-[13px] text-text-secondary">{stats.correct}/{stats.total}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
