import { motion } from "framer-motion";
import ScoreBadge from "../common/ScoreBadge";
import { pnlColor } from "../../lib/colors";
import type { StopLossAlert } from "../../lib/types";

interface HoldingCardProps {
  position: StopLossAlert;
  signal?: string;
  stopLossPct?: number;
  profitTriggered?: boolean;
  totalValue: number;
}

export default function HoldingCard({ position, signal, stopLossPct, profitTriggered, totalValue }: HoldingCardProps) {
  const pnlPct = position.pnl_pct ?? 0;
  const pnlDollar = position.pnl_dollar ?? 0;
  const positionValue = (position.shares ?? 0) * (position.current_price ?? 0);
  const isNearStop = stopLossPct != null && pnlPct < stopLossPct + 3;
  const borderClass = isNearStop
    ? "border-danger/30 hover:border-danger"
    : profitTriggered
    ? "border-caution/30 hover:border-caution"
    : "border-border hover:border-accent/50";

  const progressGlow = pnlPct >= 0
    ? "shadow-[0_0_8px_var(--color-positive-glow)]"
    : "shadow-[0_0_8px_var(--color-danger-glow)]";

  const weight = totalValue > 0 ? (positionValue / totalValue) * 100 : 0;

  return (
    <motion.div
      className={`p-3.5 rounded-lg bg-surface border ${borderClass} cursor-pointer transition-all duration-200`}
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
          {position.status === "TRIGGERED" && (
            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-danger/20 text-danger">STOP HIT</span>
          )}
        </div>
        <div className="text-right">
          <div className={`text-[15px] font-bold font-data ${pnlColor(pnlDollar)} ${pnlDollar >= 0 ? "glow-positive" : "glow-danger"}`}>
            {pnlDollar >= 0 ? "+" : ""}${pnlDollar.toLocaleString()}
          </div>
          <div className={`text-[11px] font-data ${pnlColor(pnlPct)}`}>
            {pnlPct >= 0 ? "+" : ""}{pnlPct.toFixed(1)}%
          </div>
        </div>
      </div>
      <div className="flex justify-between text-xs text-text-secondary font-data">
        <span>{position.shares?.toFixed(2) ?? "—"} shares · Avg ${position.entry_price?.toFixed(2) ?? "—"}</span>
        <span>${positionValue.toLocaleString(undefined, { maximumFractionDigits: 0 })} ({weight.toFixed(1)}%)</span>
      </div>
      <div className="mt-2 h-1 rounded-full bg-border overflow-hidden">
        <div
          className={`h-full rounded-full ${pnlPct >= 0 ? "bg-gradient-to-r from-positive to-accent" : "bg-danger"} ${progressGlow}`}
          style={{ width: `${Math.min(Math.max(50 + pnlPct * 2, 5), 100)}%` }}
        />
      </div>
    </motion.div>
  );
}
