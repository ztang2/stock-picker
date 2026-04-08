import { useApi } from "../hooks/useApi";
import { api } from "../lib/api";
import type { AlertsResponse } from "../lib/types";

export default function Alerts() {
  const { data, loading } = useApi<AlertsResponse>(() => api.alerts());
  if (loading) return <div className="text-text-secondary">Loading alerts...</div>;
  if (!data) return <div className="text-text-secondary">No alerts</div>;

  const severityClass: Record<string, string> = {
    critical: "bg-danger/15 text-danger",
    warning: "bg-caution/15 text-caution",
    info: "bg-accent/15 text-accent",
  };

  return (
    <div>
      <h1 className="text-xl font-bold mb-4">Alerts</h1>
      <div className="rounded-lg border border-border overflow-hidden">
        {data.current.length === 0 && (
          <div className="p-4 text-sm text-text-secondary">No active alerts</div>
        )}
        {data.current.map((a, i) => (
          <div key={i} className="px-4 py-3 border-b border-surface last:border-0 flex items-center gap-3">
            <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${severityClass[a.severity] ?? ""}`}>
              {a.severity}
            </span>
            <span className="text-sm font-semibold text-text-primary">{a.ticker}</span>
            <span className="text-sm text-text-secondary flex-1">{a.message}</span>
            <span className="text-xs text-text-muted">{new Date(a.timestamp).toLocaleTimeString()}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
