import type { DiversificationResponse } from "../../lib/types";

interface RebalanceSuggestionsProps {
  data: DiversificationResponse;
}

export default function RebalanceSuggestions({ data }: RebalanceSuggestionsProps) {
  if (data.suggestions.length === 0) {
    return (
      <div className="p-4 rounded-xl bg-surface border border-border text-sm text-text-secondary">
        Portfolio is well balanced — no rebalance needed
      </div>
    );
  }

  return (
    <div className="p-4 rounded-xl bg-surface border border-border">
      <div className="text-xs font-semibold text-text-primary mb-3">Rebalance Suggestions</div>
      {data.suggestions.map((s, i) => (
        <div key={i} className="flex items-start gap-2 mb-2 last:mb-0">
          <span className="text-caution text-xs mt-0.5">→</span>
          <span className="text-xs text-text-secondary">{s}</span>
        </div>
      ))}
    </div>
  );
}
