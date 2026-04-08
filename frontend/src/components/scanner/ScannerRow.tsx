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
  isWatched?: boolean;
  onToggleWatch?: (ticker: string) => void;
}

export default function ScannerRow({ stock, rank, sparkline, scoreDelta, onClick, isWatched, onToggleWatch }: ScannerRowProps) {
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

  const scoreGlow = (score: number) => {
    if (score > 75) return "glow-positive";
    if (score < 50) return "glow-danger";
    return "";
  };

  return (
    <motion.tr
      onClick={onClick}
      className="border-t border-surface cursor-pointer transition-colors hover:bg-white/[0.03] hover:border-l-2 hover:border-l-accent/30"
      whileHover={{ y: -1 }}
    >
      <td className="py-2.5 px-1.5 text-center w-8">
        <button
          onClick={(e) => { e.stopPropagation(); onToggleWatch?.(stock.ticker); }}
          className={`text-sm transition-colors ${isWatched ? "text-caution" : "text-text-muted/30 hover:text-caution/60"}`}
          title={isWatched ? "Remove from watchlist" : "Add to watchlist"}
        >
          {isWatched ? "★" : "☆"}
        </button>
      </td>
      <td className="py-2.5 px-3 font-bold text-text-primary font-data">{rank}</td>
      <td className="py-2.5 px-3">
        <div className="font-bold text-text-primary">{stock.ticker}</div>
        <div className="text-[11px] text-text-muted">{stock.name}</div>
        {stock.thesis && (
          <div className="text-[10px] text-accent/70 truncate max-w-[220px] mt-0.5">{stock.thesis}</div>
        )}
      </td>
      <td className="py-2.5 px-3">
        <RadarChart scores={scores} size={72} showLabels={true} />
      </td>
      <td className="py-2.5 px-3">
        <span className={`text-lg font-bold font-data ${scoreColor(stock.composite_score)} ${scoreGlow(stock.composite_score)}`}>
          {Math.round(stock.composite_score)}
        </span>
        <span className={`text-[11px] ml-1 font-data ${deltaColor}`}>{deltaStr}</span>
      </td>
      <td className="py-2.5 px-3 w-44">
        <SparklineBar values={sparkline} />
      </td>
      <td className="py-2.5 px-3">
        <ScoreBadge signal={stock.entry_signal} />
      </td>
      <td className="py-2.5 px-3 font-semibold text-text-primary font-data">${stock.current_price?.toFixed(2) ?? "—"}</td>
      <td className="py-2.5 px-3">
        {(stock.ma50 ?? 0) > 0 && (stock.current_price ?? 0) > 0 && (
          <span className={`font-semibold font-data ${pnlColor(stock.current_price - stock.ma50)}`}>
            {((stock.current_price / stock.ma50 - 1) * 100).toFixed(1)}%
          </span>
        )}
      </td>
      <td className="py-2.5 px-3">
        {stock.consecutive_days > 0 ? (
          <span className="text-xs text-text-secondary font-data">🔥 {stock.consecutive_days}d</span>
        ) : (
          <span className="text-xs text-text-secondary">—</span>
        )}
      </td>
    </motion.tr>
  );
}
