import type { DiversificationResponse } from "../../lib/types";
import { scoreHex } from "../../lib/colors";

interface DiversificationScoreProps {
  data: DiversificationResponse;
}

export default function DiversificationScore({ data }: DiversificationScoreProps) {
  const color = scoreHex(data.score);
  const circumference = 2 * Math.PI * 40;
  const offset = circumference * (1 - data.score / 100);

  return (
    <div className="p-4 rounded-xl bg-surface border border-border">
      <div className="text-xs font-semibold text-text-primary mb-3">Diversification Score</div>
      <div className="flex items-center gap-4">
        <svg width="100" height="100" viewBox="0 0 100 100">
          <circle cx="50" cy="50" r="40" fill="none" stroke="#334155" strokeWidth="6" />
          <circle
            cx="50" cy="50" r="40" fill="none" stroke={color} strokeWidth="6"
            strokeDasharray={circumference} strokeDashoffset={offset}
            strokeLinecap="round" transform="rotate(-90 50 50)"
          />
          <text x="50" y="50" textAnchor="middle" dominantBaseline="central" fill={color} fontSize="22" fontWeight="800">
            {Math.round(data.score)}
          </text>
        </svg>
        <div className="flex-1">
          {data.dragging_factors.map((f, i) => (
            <div key={i} className="text-xs text-text-secondary mb-1">• {f}</div>
          ))}
          {data.suggestions.map((s, i) => (
            <div key={i} className="text-xs text-caution mt-1">→ {s}</div>
          ))}
        </div>
      </div>
    </div>
  );
}
