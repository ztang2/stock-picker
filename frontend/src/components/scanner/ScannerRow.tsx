import { motion } from "framer-motion";
import type { Stock } from "../../lib/types";
import RadarChart from "../common/RadarChart";
import ScoreBadge from "../common/ScoreBadge";
import SparklineBar from "../common/SparklineBar";
import { scoreColor, pnlColor } from "../../lib/colors";

interface ScannerRowProps {
  stock: Stock;
  rank: number;
  sparkline: number[];
  scoreDelta: number | null;
  onClick: () => void;
}

export default function ScannerRow({ stock, rank, sparkline, scoreDelta, onClick }: ScannerRowProps) {
  const scores = {
    fund: stock.fundamentals_pct,
    val: stock.valuation_pct,
    tech: stock.technicals_pct,
    risk: stock.risk_pct,
    grow: stock.growth_pct,
  };

  const deltaStr = scoreDelta !== null && scoreDelta !== 0
    ? scoreDelta > 0 ? `▲${scoreDelta}` : `▼${Math.abs(scoreDelta)}`
    : "—";
  const deltaColor = scoreDelta !== null && scoreDelta > 0
    ? "text-positive" : scoreDelta !== null && scoreDelta < 0
    ? "text-danger" : "text-text-secondary";

  return (
    <motion.tr
      onClick={onClick}
      className="border-t border-surface cursor-pointer transition-colors hover:bg-accent/5"
      whileHover={{ y: -1 }}
    >
      <td className="py-2.5 px-3 font-bold text-text-primary">{rank}</td>
      <td className="py-2.5 px-3">
        <div className="font-bold text-text-primary">{stock.ticker}</div>
        <div className="text-[11px] text-text-muted">{stock.name}</div>
      </td>
      <td className="py-2.5 px-3">
        <RadarChart scores={scores} size={72} showLabels={true} />
      </td>
      <td className="py-2.5 px-3">
        <span className={`text-lg font-bold ${scoreColor(stock.composite_score)}`}>
          {Math.round(stock.composite_score)}
        </span>
        <span className={`text-[11px] ml-1 ${deltaColor}`}>{deltaStr}</span>
      </td>
      <td className="py-2.5 px-3 w-44">
        <SparklineBar values={sparkline} />
      </td>
      <td className="py-2.5 px-3">
        <ScoreBadge signal={stock.entry_signal} />
      </td>
      <td className="py-2.5 px-3 font-semibold text-text-primary">${stock.current_price?.toFixed(2) ?? "—"}</td>
      <td className="py-2.5 px-3">
        {(stock.ma50 ?? 0) > 0 && (stock.current_price ?? 0) > 0 && (
          <span className={`font-semibold ${pnlColor(stock.current_price - stock.ma50)}`}>
            {((stock.current_price / stock.ma50 - 1) * 100).toFixed(1)}%
          </span>
        )}
      </td>
      <td className="py-2.5 px-3">
        {stock.consecutive_days > 0 ? (
          <span className="text-xs text-text-secondary">🔥 {stock.consecutive_days}d</span>
        ) : (
          <span className="text-xs text-text-secondary">—</span>
        )}
      </td>
    </motion.tr>
  );
}
