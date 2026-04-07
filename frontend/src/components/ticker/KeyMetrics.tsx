import type { Stock } from "../../lib/types";
import MetricCard from "../common/MetricCard";
import { scoreColor } from "../../lib/colors";

interface KeyMetricsProps {
  stock: Stock;
}

export default function KeyMetrics({ stock }: KeyMetricsProps) {
  const rsi = stock.rsi ?? 0;
  const rsiColor = rsi > 70 ? "text-danger" : rsi < 30 ? "text-positive" : "text-text-primary";
  const mlColor = stock.ml_signal === "outperform" ? "text-positive" : "text-text-secondary";
  const sentiment = stock.sentiment;
  const ma50 = stock.ma50 ?? 0;

  return (
    <div className="grid grid-cols-3 gap-2.5">
      <MetricCard label="RSI (14)" value={rsi.toFixed(1)} subtitle={rsi > 70 ? "Overbought" : rsi < 30 ? "Oversold" : "Neutral"} valueColor={rsiColor} />
      <MetricCard label="Valuation" value={(stock.valuation_pct ?? 0) > 0 ? (stock.valuation_pct ?? 0).toFixed(0) : "N/A"} subtitle={`Valuation score: ${(stock.valuation_pct ?? 0).toFixed(0)}`} />
      <MetricCard label="ML Confidence" value={stock.ml_score != null ? stock.ml_score.toFixed(2) : "N/A"} subtitle={stock.ml_signal ?? "No prediction"} valueColor={mlColor} />
      <MetricCard label="Growth Score" value={(stock.growth_pct ?? 0).toFixed(0)} subtitle="Percentile rank" valueColor={scoreColor(stock.growth_pct ?? 0)} />
      <MetricCard
        label="Support (MA50)"
        value={ma50 > 0 ? `$${ma50.toFixed(2)}` : "N/A"}
        subtitle={ma50 > 0 ? `${((stock.current_price / ma50 - 1) * 100).toFixed(1)}% ${stock.above_ma50 ? "above" : "below"}` : ""}
      />
      <MetricCard
        label="Analyst Target"
        value={sentiment?.pt_upside_pct > 0 ? `+${(sentiment.pt_upside_pct * 100).toFixed(1)}%` : "N/A"}
        subtitle={sentiment ? `${sentiment.analyst_count} analysts · ${sentiment.recommendation}` : "No data"}
        valueColor={sentiment?.pt_upside_pct > 0.1 ? "text-positive" : "text-text-secondary"}
      />
    </div>
  );
}
