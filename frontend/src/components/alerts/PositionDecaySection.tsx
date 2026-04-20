import { useApi } from "../../hooks/useApi";
import { api, type DecayAlert, type DecayAlertsResponse } from "../../lib/api";
import { pnlColor } from "../../lib/colors";
import { AlertTriangle, AlertCircle, Info } from "lucide-react";

const SEVERITY_META: Record<DecayAlert["severity"], { cls: string; Icon: typeof AlertTriangle; label: string }> = {
  urgent: { cls: "border-danger/40 bg-danger/8 text-danger", Icon: AlertCircle, label: "URGENT" },
  warning: { cls: "border-caution/40 bg-caution/8 text-caution", Icon: AlertTriangle, label: "WARNING" },
  info: { cls: "border-accent/30 bg-accent/8 text-accent", Icon: Info, label: "INFO" },
};

export default function PositionDecaySection() {
  const { data, loading } = useApi<DecayAlertsResponse>(() => api.decayAlerts());
  if (loading) return null;
  if (!data) return null;

  const { alerts, summary } = data;

  return (
    <div className="mb-6">
      <div className="flex items-baseline justify-between mb-3">
        <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider">
          Position Health <span className="text-text-muted/70 font-normal">({summary.total})</span>
        </h2>
        {summary.total > 0 && (
          <div className="flex items-center gap-2 text-[11px]">
            {summary.urgent > 0 && <span className="px-2 py-0.5 rounded bg-danger/15 text-danger font-semibold">{summary.urgent} urgent</span>}
            {summary.warning > 0 && <span className="px-2 py-0.5 rounded bg-caution/15 text-caution font-semibold">{summary.warning} warning</span>}
            {summary.info > 0 && <span className="px-2 py-0.5 rounded bg-accent/15 text-accent font-semibold">{summary.info} info</span>}
          </div>
        )}
      </div>

      {alerts.length === 0 ? (
        <div className="p-4 rounded-lg bg-surface border border-border text-sm text-text-secondary text-center">
          All held positions healthy — no degradation, sell signals, or stop-loss proximity detected.
        </div>
      ) : (
        <div className="space-y-2">
          {alerts.map((a, i) => {
            const meta = SEVERITY_META[a.severity];
            const Icon = meta.Icon;
            return (
              <div
                key={`${a.ticker}-${a.alert_type}-${i}`}
                className={`p-3.5 rounded-lg border ${meta.cls.split(" ").slice(0, 2).join(" ")}`}
              >
                <div className="flex items-start gap-3">
                  <Icon size={16} className={meta.cls.split(" ")[2]} strokeWidth={2.25} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold tracking-wider ${meta.cls}`}>
                        {meta.label}
                      </span>
                      <span className="text-[15px] font-bold text-text-primary">{a.ticker}</span>
                      {a.current_signal && (
                        <span className="text-[11px] font-mono text-text-muted">
                          {a.previous_signal && a.previous_signal !== a.current_signal
                            ? `${a.previous_signal} → ${a.current_signal}`
                            : a.current_signal}
                        </span>
                      )}
                    </div>
                    <div className="text-sm text-text-secondary">{a.message}</div>
                    <div className="mt-2 grid grid-cols-2 sm:grid-cols-4 gap-x-4 gap-y-1 text-[11px] font-data">
                      <KV label="Score" value={`${a.current_score.toFixed(1)}${a.score_delta ? ` (${a.score_delta >= 0 ? "+" : ""}${a.score_delta.toFixed(1)})` : ""}`} />
                      <KV label="Price" value={a.current_price != null ? `$${a.current_price.toFixed(2)}` : "—"} />
                      <KV label="P&L" value={`${a.pnl_pct >= 0 ? "+" : ""}${a.pnl_pct.toFixed(2)}%`} valueClass={pnlColor(a.pnl_pct)} />
                      <KV label="Entry" value={`$${a.entry_price.toFixed(2)}${a.entry_score ? ` @ ${a.entry_score.toFixed(0)}` : ""}`} />
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function KV({ label, value, valueClass }: { label: string; value: string; valueClass?: string }) {
  return (
    <div>
      <span className="text-text-muted uppercase tracking-wider text-[9px]">{label}</span>{" "}
      <span className={valueClass || "text-text-primary"}>{value}</span>
    </div>
  );
}
