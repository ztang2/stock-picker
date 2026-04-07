import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { Stock } from "../../lib/types";
import RadarChart from "../common/RadarChart";
import ScoreBadge from "../common/ScoreBadge";
import SynthesisBanner from "./SynthesisBanner";
import KeyMetrics from "./KeyMetrics";
import { scoreColor } from "../../lib/colors";
import EntryTiming from "./EntryTiming";
import DCFTab from "./DCFTab";
import CompsTab from "./CompsTab";
import EarningsTab from "./EarningsTab";
import MomentumTab from "./MomentumTab";
import DevilTab from "./DevilTab";

const TABS = ["Entry Timing", "DCF Valuation", "Peer Comps", "Earnings", "Momentum", "Devil's Advocate"] as const;

interface TickerModalProps {
  stock: Stock;
  onClose: () => void;
}

export default function TickerModal({ stock, onClose }: TickerModalProps) {
  const [activeTab, setActiveTab] = useState<typeof TABS[number]>("Entry Timing");

  const scores = {
    fund: stock.fundamentals_pct,
    val: stock.valuation_pct,
    tech: stock.technicals_pct,
    risk: stock.risk_pct,
    grow: stock.growth_pct,
  };

  function renderTab() {
    switch (activeTab) {
      case "Entry Timing": return <EntryTiming ticker={stock.ticker} />;
      case "DCF Valuation": return <DCFTab ticker={stock.ticker} />;
      case "Peer Comps": return <CompsTab ticker={stock.ticker} />;
      case "Earnings": return <EarningsTab ticker={stock.ticker} />;
      case "Momentum": return <MomentumTab ticker={stock.ticker} />;
      case "Devil's Advocate": return <DevilTab ticker={stock.ticker} />;
    }
  }

  return (
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 bg-black/60 z-50 flex items-start justify-center pt-8 overflow-auto"
        onClick={onClose}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
      >
        <motion.div
          className="bg-base border border-border rounded-2xl w-full max-w-4xl mb-8 overflow-hidden"
          onClick={(e) => e.stopPropagation()}
          initial={{ scale: 0.95, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.95, opacity: 0 }}
        >
          <div className="flex justify-between items-start p-5 border-b border-surface">
            <div>
              <div className="flex items-center gap-3 mb-1">
                <span className="text-2xl font-bold text-text-primary">{stock.ticker}</span>
                <ScoreBadge signal={stock.entry_signal} />
                {stock.consecutive_days > 0 && (
                  <span className="px-2.5 py-1 rounded-md bg-caution/15 text-caution text-xs font-semibold">
                    🔥 {stock.consecutive_days}d streak
                  </span>
                )}
              </div>
              <div className="text-sm text-text-secondary">{stock.name} · {stock.sector}</div>
            </div>
            <div className="text-right">
              <div className="text-2xl font-bold text-text-primary">${stock.current_price.toFixed(2)}</div>
              <button onClick={onClose} className="text-text-muted hover:text-text-primary text-xs mt-1">✕ Close</button>
            </div>
          </div>

          <SynthesisBanner text={stock.synthesis} />

          <div className="grid grid-cols-[220px_1fr] gap-4 px-6 pb-4">
            <div className="p-4 rounded-xl bg-surface border border-border flex flex-col items-center">
              <div className="text-[11px] text-text-muted uppercase tracking-wider font-semibold mb-2">Score Profile</div>
              <RadarChart scores={scores} size={170} showLabels={true} />
              <div className={`mt-1 text-3xl font-extrabold ${scoreColor(stock.composite_score)}`}>
                {Math.round(stock.composite_score)}
              </div>
              <div className="text-[11px] text-text-secondary">Overall Score</div>
            </div>
            <KeyMetrics stock={stock} />
          </div>

          <div className="px-6 pb-5">
            <div className="flex gap-0.5 mb-4 bg-surface rounded-lg p-1">
              {TABS.map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`px-4 py-2 rounded-md text-xs font-semibold transition-colors ${
                    activeTab === tab ? "bg-accent text-white" : "text-text-secondary hover:text-text-primary"
                  }`}
                >
                  {tab}
                </button>
              ))}
            </div>
            <div className="rounded-xl bg-surface border border-border overflow-hidden">
              {renderTab()}
            </div>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
