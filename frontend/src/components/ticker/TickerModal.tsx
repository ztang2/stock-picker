import { useState, Component, type ReactNode, type ErrorInfo } from "react";
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
import PriceChart from "./PriceChart";
import PositionSizer from "./PositionSizer";

class TabErrorBoundary extends Component<
  { children: ReactNode; tabName: string },
  { error: string | null }
> {
  state = { error: null as string | null };

  static getDerivedStateFromError(error: Error) {
    return { error: error.message };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`Tab crash [${this.props.tabName}]:`, error, info);
  }

  componentDidUpdate(prevProps: { tabName: string }) {
    if (prevProps.tabName !== this.props.tabName) {
      this.setState({ error: null });
    }
  }

  render() {
    if (this.state.error) {
      return (
        <div className="p-4 text-text-secondary text-sm">
          Failed to load tab: {this.state.error}
        </div>
      );
    }
    return this.props.children;
  }
}

const TABS = ["Entry Timing", "DCF Valuation", "Peer Comps", "Earnings", "Momentum", "Devil's Advocate"] as const;

interface TickerModalProps {
  stock: Stock;
  onClose: () => void;
}

export default function TickerModal({ stock, onClose }: TickerModalProps) {
  const [activeTab, setActiveTab] = useState<typeof TABS[number]>("Entry Timing");

  const scores = {
    fund: stock?.fundamentals_pct ?? 0,
    val: stock?.valuation_pct ?? 0,
    tech: stock?.technicals_pct ?? 0,
    risk: stock?.risk_pct ?? 0,
    grow: stock?.growth_pct ?? 0,
  };

  const compositeScore = Math.round(stock?.composite_score ?? 0);
  const scoreGrade = compositeScore >= 80 ? "A" : compositeScore >= 65 ? "B" : compositeScore >= 50 ? "C" : "D";

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
        className="fixed inset-0 z-50 flex items-start justify-center pt-6 overflow-auto backdrop-blur-xl bg-base/80"
        onClick={onClose}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
      >
        <motion.div
          className="w-full max-w-[960px] mb-8 rounded-xl overflow-hidden bg-surface border border-border"
          style={{
            boxShadow: "0 0 0 1px rgba(161,120,50,0.08), 0 32px 100px rgba(0,0,0,0.15)",
          }}
          onClick={(e) => e.stopPropagation()}
          initial={{ y: 20, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: 20, opacity: 0 }}
          transition={{ duration: 0.25, ease: [0.23, 1, 0.32, 1] }}
        >
          {/* Header — editorial ticker display */}
          <div className="relative px-6 pt-5 pb-4">
            <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-accent/20 to-transparent" />
            <div className="flex justify-between items-start">
              <div className="flex items-baseline gap-4">
                <span className="text-3xl font-extrabold tracking-tight text-text-primary">{stock?.ticker}</span>
                <span className="text-2xl font-bold font-data text-text-primary">${stock?.current_price?.toFixed(2) ?? "—"}</span>
                <ScoreBadge signal={stock?.entry_signal ?? "HOLD"} />
                {(stock?.consecutive_days ?? 0) > 0 && (
                  <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-caution/10 text-caution border border-caution/20">
                    {stock.consecutive_days}d streak
                  </span>
                )}
              </div>
              <div className="flex items-center gap-3">
                <div className="text-right">
                  <div className={`text-2xl font-extrabold font-data ${scoreColor(compositeScore)}`}>
                    {compositeScore}
                    <span className="text-sm font-semibold text-text-muted ml-1">{scoreGrade}</span>
                  </div>
                </div>
                <button
                  onClick={onClose}
                  className="w-8 h-8 rounded-lg bg-surface-raised/50 flex items-center justify-center text-text-muted hover:text-text-primary hover:bg-surface-raised transition-all"
                >
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M1 1l12 12M13 1L1 13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
                </button>
              </div>
            </div>
            <div className="text-[13px] text-text-muted mt-1 font-light">{stock?.name} · {stock?.sector}</div>
          </div>

          <SynthesisBanner text={stock?.synthesis} />

          {/* Chart + Sizer — side by side */}
          <div className="px-5 pt-3 pb-2 grid grid-cols-[1.8fr_1fr] gap-3">
            <PriceChart ticker={stock.ticker} />
            <PositionSizer ticker={stock.ticker} currentPrice={stock.current_price ?? 0} />
          </div>

          {/* Scores row — compact horizontal */}
          <div className="px-5 pb-3">
            <div className="flex gap-3">
              <div className="shrink-0 p-3 rounded-lg bg-surface flex flex-col items-center border border-border">
                <RadarChart scores={scores} size={130} showLabels={true} />
              </div>
              <div className="flex-1">
                <KeyMetrics stock={stock} />
              </div>
            </div>
          </div>

          {/* Tabs — underline style */}
          <div className="px-5 pb-5">
            <div className="flex gap-1 mb-3 border-b border-border">
              {TABS.map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`px-3 py-2.5 text-xs font-medium transition-all relative ${
                    activeTab === tab
                      ? "text-accent"
                      : "text-text-muted hover:text-text-secondary"
                  }`}
                >
                  {tab}
                  {activeTab === tab && (
                    <motion.div
                      layoutId="tab-indicator"
                      className="absolute bottom-0 left-0 right-0 h-[2px] bg-accent"
                      style={{ borderRadius: "1px 1px 0 0" }}
                    />
                  )}
                </button>
              ))}
            </div>
            <div className="rounded-lg bg-surface border border-border overflow-hidden">
              <TabErrorBoundary tabName={activeTab}>
                {renderTab()}
              </TabErrorBoundary>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
