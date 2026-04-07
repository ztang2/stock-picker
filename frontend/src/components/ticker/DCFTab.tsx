import { useApi } from "../../hooks/useApi";
import { pnlColor } from "../../lib/colors";

interface DCFData {
  intrinsic_value?: number;
  current_price?: number;
  margin_of_safety?: number;
  upside_pct?: number;
  verdict?: string;
  wacc?: number;
  growth_rate?: number;
  confidence?: string;
  fcf_yield_pct?: number;
}

const VERDICT_COLOR: Record<string, string> = {
  UNDERVALUED: "text-positive",
  FAIRLY_VALUED: "text-caution",
  OVERVALUED: "text-danger",
};

export default function DCFTab({ ticker }: { ticker: string }) {
  const { data, loading, error } = useApi<DCFData>(
    () => fetch(`/dcf/${ticker}/summary`).then(r => r.json()),
    [ticker]
  );
  if (loading) return <div className="p-4 text-text-secondary text-sm">Loading DCF...</div>;
  if (error || !data) return <div className="p-4 text-text-secondary text-sm">DCF data unavailable</div>;

  return (
    <div className="p-4">
      <div className="flex items-center gap-3 mb-4">
        <span className={`text-lg font-bold ${VERDICT_COLOR[data.verdict ?? ""] ?? "text-text-primary"}`}>
          {data.verdict ?? "—"}
        </span>
        <span className="text-sm text-text-secondary">Confidence: {data.confidence ?? "—"}</span>
      </div>
      <div className="grid grid-cols-3 gap-3 mb-3">
        <div className="p-3 rounded-lg bg-base border border-border">
          <div className="text-[10px] text-text-muted uppercase tracking-wider">Intrinsic Value</div>
          <div className="text-xl font-bold text-text-primary mt-0.5">${data.intrinsic_value?.toFixed(2) ?? "—"}</div>
        </div>
        <div className="p-3 rounded-lg bg-base border border-border">
          <div className="text-[10px] text-text-muted uppercase tracking-wider">Current Price</div>
          <div className="text-xl font-bold text-text-primary mt-0.5">${data.current_price?.toFixed(2) ?? "—"}</div>
        </div>
        <div className="p-3 rounded-lg bg-base border border-border">
          <div className="text-[10px] text-text-muted uppercase tracking-wider">Margin of Safety</div>
          <div className={`text-xl font-bold mt-0.5 ${pnlColor(data.margin_of_safety ?? 0)}`}>{data.margin_of_safety?.toFixed(1) ?? "—"}%</div>
        </div>
      </div>
      <div className="grid grid-cols-3 gap-3">
        <div className="p-3 rounded-lg bg-base border border-border">
          <div className="text-[10px] text-text-muted uppercase tracking-wider">Upside</div>
          <div className={`text-lg font-bold mt-0.5 ${pnlColor(data.upside_pct ?? 0)}`}>
            {data.upside_pct != null ? `${data.upside_pct > 0 ? "+" : ""}${data.upside_pct.toFixed(1)}%` : "—"}
          </div>
        </div>
        <div className="p-3 rounded-lg bg-base border border-border">
          <div className="text-[10px] text-text-muted uppercase tracking-wider">WACC</div>
          <div className="text-lg font-bold text-text-primary mt-0.5">{data.wacc != null ? `${(data.wacc * 100).toFixed(1)}%` : "—"}</div>
        </div>
        <div className="p-3 rounded-lg bg-base border border-border">
          <div className="text-[10px] text-text-muted uppercase tracking-wider">FCF Yield</div>
          <div className="text-lg font-bold text-text-primary mt-0.5">{data.fcf_yield_pct?.toFixed(1) ?? "—"}%</div>
        </div>
      </div>
    </div>
  );
}
