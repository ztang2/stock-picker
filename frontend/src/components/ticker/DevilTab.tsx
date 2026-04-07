import { useApi } from "../../hooks/useApi";
import { api } from "../../lib/api";
import type { DevilsAdvocate } from "../../lib/types";

export default function DevilTab({ ticker }: { ticker: string }) {
  const { data, loading } = useApi<DevilsAdvocate>(() => api.devil(ticker), [ticker]);
  if (loading) return <div className="p-4 text-text-secondary text-sm">Loading risk review...</div>;
  if (!data) return <div className="p-4 text-text-secondary text-sm">Risk review unavailable</div>;
  return (
    <div className="p-4">
      <div className="flex gap-2 mb-3">
        <span className="px-2 py-0.5 rounded text-xs font-bold bg-danger/15 text-danger">Risk: {data.risk_score}/10</span>
        <span className="px-2 py-0.5 rounded text-xs bg-danger/15 text-danger">{data.quant_flags.red_count} red flags</span>
        <span className="px-2 py-0.5 rounded text-xs bg-positive/15 text-positive">{data.quant_flags.green_count} green flags</span>
      </div>
      <div className="text-sm text-text-primary whitespace-pre-wrap leading-relaxed">{data.review_text}</div>
    </div>
  );
}
