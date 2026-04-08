import type { CorrelationResponse } from "../../lib/types";

interface CorrelationHeatmapProps {
  data: CorrelationResponse;
}

function corrColor(val: number): string {
  if (val > 0.7) return "#ef4444";
  if (val > 0.4) return "#f59e0b";
  if (val > 0.1) return "#6366f1";
  return "#3b82f6";
}

export default function CorrelationHeatmap({ data }: CorrelationHeatmapProps) {
  if (data.tickers.length < 2) {
    return (
      <div className="p-4 rounded-lg bg-surface border border-border text-sm text-text-secondary">
        Need at least 2 holdings for correlation analysis
      </div>
    );
  }

  const size = 36;

  return (
    <div className="p-4 rounded-lg bg-surface border border-border">
      <div className="text-xs font-semibold text-text-primary mb-3">Correlation Heatmap (90-day)</div>
      <div className="overflow-auto">
        <div className="inline-grid gap-0.5" style={{ gridTemplateColumns: `60px repeat(${data.tickers.length}, ${size}px)` }}>
          <div />
          {data.tickers.map((t) => (
            <div key={t} className="text-[10px] text-text-muted text-center font-semibold">{t}</div>
          ))}
          {data.tickers.map((rowTicker, i) => (
            <div key={`row-${rowTicker}`} className="contents">
              <div className="text-[10px] text-text-muted font-semibold flex items-center">{rowTicker}</div>
              {data.matrix[i].map((val, j) => (
                <div
                  key={`${i}-${j}`}
                  className="rounded-sm flex items-center justify-center text-[9px] font-bold text-text-primary/80"
                  style={{ width: size, height: size, backgroundColor: i === j ? "var(--color-border)" : corrColor(val) }}
                  title={`${rowTicker} × ${data.tickers[j]}: ${val.toFixed(3)}`}
                >
                  {i !== j ? val.toFixed(2) : "1.0"}
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
