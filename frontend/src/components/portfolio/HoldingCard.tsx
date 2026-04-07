import { motion } from "framer-motion";
import ScoreBadge from "../common/ScoreBadge";
import { pnlColor } from "../../lib/colors";

interface Position {
  ticker: string;
  shares: number;
  entry_price: number;
  current_price: number;
  position_value: number;
  pnl: number;
  pnl_pct: number;
  risk_level: string;
}

interface HoldingCardProps {
  position: Position;
  signal?: string;
  stopLossPct?: number;
  profitTriggered?: boolean;
  totalValue: number;
}

export default function HoldingCard({ position, signal, stopLossPct, profitTriggered, totalValue }: HoldingCardProps) {
  const isNearStop = stopLossPct != null && position.pnl_pct < stopLossPct + 3;
  const borderClass = isNearStop
    ? "border-danger/30 hover:border-danger"
    : profitTriggered
    ? "border-caution/30 hover:border-caution"
    : "border-border hover:border-accent";

  const weight = totalValue > 0 ? (position.position_value / totalValue) * 100 : 0;

  return (
    <motion.div
      className={`p-3.5 rounded-xl bg-surface border ${borderClass} cursor-pointer transition-all duration-200`}
      whileHover={{ y: -1 }}
    >
      <div className="flex justify-between items-center mb-2">
        <div className="flex items-center gap-2.5">
          <span className="text-[15px] font-bold text-text-primary">{position.ticker}</span>
          {signal && <ScoreBadge signal={signal} />}
          {isNearStop && (
            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-danger/12 text-danger">NEAR STOP</span>
          )}
          {profitTriggered && (
            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-caution/12 text-caution">PROFIT T1</span>
          )}
        </div>
        <div className="text-right">
          <div className={`text-[15px] font-bold ${pnlColor(position.pnl)}`}>
            {position.pnl >= 0 ? "+" : ""}${position.pnl.toLocaleString()}
          </div>
          <div className={`text-[11px] ${pnlColor(position.pnl_pct)}`}>
            {position.pnl_pct >= 0 ? "+" : ""}{position.pnl_pct.toFixed(1)}%
          </div>
        </div>
      </div>
      <div className="flex justify-between text-xs text-text-secondary">
        <span>{position.shares} shares · Avg ${position.entry_price.toFixed(2)}</span>
        <span>${position.position_value.toLocaleString()} ({weight.toFixed(1)}%)</span>
      </div>
      <div className="mt-2 h-1 rounded-full bg-border overflow-hidden">
        <div
          className={`h-full rounded-full ${position.pnl >= 0 ? "bg-gradient-to-r from-positive to-accent" : "bg-danger"}`}
          style={{ width: `${Math.min(Math.max(50 + position.pnl_pct * 2, 5), 100)}%` }}
        />
      </div>
    </motion.div>
  );
}
