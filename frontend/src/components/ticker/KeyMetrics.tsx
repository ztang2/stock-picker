import type { Stock } from "../../lib/types";
import MetricCard from "../common/MetricCard";
import { scoreColor } from "../../lib/colors";

interface KeyMetricsProps {
  stock: Stock;
}

export default function KeyMetrics({ stock }: KeyMetricsProps) {
  const rsiColor = stock.rsi > 70 ? "text-danger" : stock.rsi < 30 ? "text-positive" : "text-text-primary";
  const mlColor = stock.ml_signal === "outperform" ? "text-positive" : "text-text-secondary";

  return (
    <div className="grid grid-cols-3 gap-2.5">
      <MetricCard label="RSI (14)" value={stock.rsi.toFixed(1)} subtitle={stock.rsi > 70 ? "Overbought" : stock.rsi < 30 ? "Oversold" : "Neutral"} valueColor={rsiColor} />
      <MetricCard label="P/E Ratio" value={stock.valuation_pct > 0 ? stock.valuation_pct.toFixed(0) : "N/A"} subtitle={`Valuation score: ${stock.valuation_pct.toFixed(0)}`} />
      <MetricCard label="ML Confidence" value={stock.ml_score != null ? stock.ml_score.toFixed(2) : "N/A"} subtitle={stock.ml_signal ?? "No prediction"} valueColor={mlColor} />
      <MetricCard label="Growth Score" value={stock.growth_pct.toFixed(0)} subtitle="Percentile rank" valueColor={scoreColor(stock.growth_pct)} />
      <MetricCard
        label="Support (MA50)"
        value={`$${stock.ma50.toFixed(2)}`}
        subtitle={`${((stock.current_price / stock.ma50 - 1) * 100).toFixed(1)}% ${stock.above_ma50 ? "above" : "below"}`}
      />
      <MetricCard
        label="Analyst Target"
        value={stock.sentiment.pt_upside_pct > 0 ? `+${(stock.sentiment.pt_upside_pct * 100).toFixed(1)}%` : "N/A"}
        subtitle={`${stock.sentiment.analyst_count} analysts · ${stock.sentiment.recommendation}`}
        valueColor={stock.sentiment.pt_upside_pct > 0.1 ? "text-positive" : "text-text-secondary"}
      />
    </div>
  );
}
