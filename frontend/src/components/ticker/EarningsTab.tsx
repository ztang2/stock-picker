import { useApi } from "../../hooks/useApi";
import { pnlColor } from "../../lib/colors";

interface BeatMiss {
  quarter?: string;
  eps_estimate?: number;
  eps_actual?: number;
  surprise_pct?: number;
  beat?: boolean;
}

interface QuarterlyData {
  period?: string;
  revenue?: number;
  net_income?: number;
  gross_margin?: number;
  net_margin?: number;
}

interface EarningsData {
  ticker: string;
  beat_rate?: number;
  beat_count?: number;
  miss_count?: number;
  beat_miss_history?: BeatMiss[];
  quarterly_data?: QuarterlyData[];
  earnings_quality_score?: number;
  revenue_growth_trend?: { latest_yoy?: number; avg_yoy?: number; trend?: string } | string;
  margin_trend?: { latest?: number; previous?: number; trend?: string } | string;
}

function fmtB(val: number | null | undefined): string {
  if (val == null) return "—";
  if (Math.abs(val) >= 1e9) return `$${(val / 1e9).toFixed(1)}B`;
  if (Math.abs(val) >= 1e6) return `$${(val / 1e6).toFixed(0)}M`;
  return `$${val.toFixed(0)}`;
}

export default function EarningsTab({ ticker }: { ticker: string }) {
  const { data, loading, error } = useApi<EarningsData>(
    () => fetch(`/earnings/${ticker}/analysis`).then(r => r.json()),
    [ticker]
  );
  if (loading) return <div className="p-4 text-text-secondary text-sm">Loading earnings...</div>;
  if (error || !data) return <div className="p-4 text-text-secondary text-sm">Earnings data unavailable</div>;

  return (
    <div className="p-4">
      {/* Summary row */}
      <div className="grid grid-cols-4 gap-3 mb-4">
        <div className="p-3 rounded-lg bg-base border border-border">
          <div className="text-[10px] text-text-muted uppercase tracking-wider">Beat Rate</div>
          <div className="text-xl font-bold text-positive mt-0.5">{data.beat_rate?.toFixed(0) ?? "—"}%</div>
          <div className="text-[11px] text-text-secondary">{data.beat_count ?? 0} beats / {data.miss_count ?? 0} misses</div>
        </div>
        <div className="p-3 rounded-lg bg-base border border-border">
          <div className="text-[10px] text-text-muted uppercase tracking-wider">Quality Score</div>
          <div className="text-xl font-bold text-text-primary mt-0.5">{data.earnings_quality_score?.toFixed(0) ?? "—"}</div>
        </div>
        <div className="p-3 rounded-lg bg-base border border-border">
          <div className="text-[10px] text-text-muted uppercase tracking-wider">Revenue Trend</div>
          <div className="text-sm font-semibold text-text-primary mt-1">
            {typeof data.revenue_growth_trend === "object" && data.revenue_growth_trend
              ? `${data.revenue_growth_trend.trend ?? "—"} (YoY ${data.revenue_growth_trend.latest_yoy?.toFixed(0) ?? "—"}%)`
              : String(data.revenue_growth_trend ?? "—")}
          </div>
        </div>
        <div className="p-3 rounded-lg bg-base border border-border">
          <div className="text-[10px] text-text-muted uppercase tracking-wider">Margin Trend</div>
          <div className="text-sm font-semibold text-text-primary mt-1">
            {typeof data.margin_trend === "object" && data.margin_trend
              ? `${data.margin_trend.trend ?? "—"} (${data.margin_trend.latest?.toFixed(1) ?? "—"}%)`
              : String(data.margin_trend ?? "—")}
          </div>
        </div>
      </div>

      {/* Beat/Miss History */}
      {(data.beat_miss_history ?? []).length > 0 && (
        <div className="mb-4">
          <div className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">EPS Surprise History</div>
          <div className="flex gap-2">
            {(data.beat_miss_history ?? []).map((q, i) => (
              <div key={i} className={`flex-1 p-2.5 rounded-lg border ${q.beat ? "bg-positive/5 border-positive/20" : "bg-danger/5 border-danger/20"}`}>
                <div className={`text-xs font-bold ${q.beat ? "text-positive" : "text-danger"}`}>
                  {q.beat ? "BEAT" : "MISS"}
                </div>
                <div className="text-[11px] text-text-secondary mt-1">
                  Est: ${q.eps_estimate?.toFixed(2) ?? "—"}
                </div>
                <div className="text-[11px] text-text-primary">
                  Act: ${q.eps_actual?.toFixed(2) ?? "—"}
                </div>
                <div className={`text-[11px] font-semibold ${pnlColor(q.surprise_pct ?? 0)}`}>
                  {q.surprise_pct != null ? `${q.surprise_pct > 0 ? "+" : ""}${(q.surprise_pct * 100).toFixed(1)}%` : "—"}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Quarterly Financials */}
      {(data.quarterly_data ?? []).length > 0 && (
        <div>
          <div className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">Quarterly Financials</div>
          <div className="rounded-lg border border-border overflow-hidden">
            <table className="w-full text-xs">
              <thead className="bg-base">
                <tr>
                  <th className="py-2 px-3 text-left text-text-muted uppercase">Period</th>
                  <th className="py-2 px-3 text-right text-text-muted uppercase">Revenue</th>
                  <th className="py-2 px-3 text-right text-text-muted uppercase">Net Income</th>
                  <th className="py-2 px-3 text-right text-text-muted uppercase">Gross Margin</th>
                  <th className="py-2 px-3 text-right text-text-muted uppercase">Net Margin</th>
                </tr>
              </thead>
              <tbody>
                {(data.quarterly_data ?? []).map((q, i) => (
                  <tr key={i} className="border-t border-border">
                    <td className="py-2 px-3 text-text-primary">{q.period ?? "—"}</td>
                    <td className="py-2 px-3 text-right text-text-primary">{fmtB(q.revenue)}</td>
                    <td className={`py-2 px-3 text-right ${pnlColor(q.net_income ?? 0)}`}>{fmtB(q.net_income)}</td>
                    <td className="py-2 px-3 text-right text-text-primary">{q.gross_margin?.toFixed(1) ?? "—"}%</td>
                    <td className="py-2 px-3 text-right text-text-primary">{q.net_margin?.toFixed(1) ?? "—"}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
