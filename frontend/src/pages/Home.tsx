import { motion } from "framer-motion";
import { useState, useCallback } from "react";
import { useScan } from "../App";
import { useApi } from "../hooks/useApi";
import { useTimeOfDay } from "../hooks/useTimeOfDay";
import { api } from "../lib/api";
import SummaryCards from "../components/home/SummaryCards";
import ActionItems from "../components/home/ActionItems";
import NewSignals from "../components/home/NewSignals";
import MarketPulse from "../components/home/MarketPulse";
import HoldingsStrip from "../components/home/HoldingsStrip";
import TickerModal from "../components/ticker/TickerModal";
import type { AlertsResponse, AccuracyResponse, RiskSummary, StopLossAlert, Stock } from "../lib/types";

const GREETING: Record<string, string> = {
  morning: "Good morning",
  midday: "Good afternoon",
  evening: "Good evening",
};

const stagger = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.06 } },
};

const fadeUp = {
  hidden: { opacity: 0, y: 16 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: "easeOut" as const } },
};

export default function Home() {
  const { scan, loading, refetch } = useScan();
  const tod = useTimeOfDay();
  const [scanning, setScanning] = useState(false);

  const runScan = useCallback(async () => {
    if (scanning) return;
    setScanning(true);
    try {
      await fetch("/scan?force=true", { headers: { "X-API-Key": "stock-picker" } });
      // poll status until done
      let done = false;
      while (!done) {
        await new Promise((r) => setTimeout(r, 1500));
        const res = await fetch("/scan/status");
        const data = await res.json();
        if (data.status === "idle" || data.status === "done") done = true;
      }
      refetch();
    } finally {
      setScanning(false);
    }
  }, [scanning, refetch]);
  const { data: alerts } = useApi<AlertsResponse>(() => api.alerts());
  const { data: accuracy } = useApi<AccuracyResponse>(() => api.accuracy());
  const { data: risk } = useApi<RiskSummary>(() => api.riskSummary());
  const { data: stopLosses } = useApi<{ alerts: StopLossAlert[] }>(() => api.stopLosses());

  const [selectedStock, setSelectedStock] = useState<Stock | null>(null);

  const handleTickerClick = (ticker: string) => {
    const stock = scan?.top.find(s => s.ticker === ticker) ?? scan?.all_scores.find(s => s.ticker === ticker);
    if (stock) setSelectedStock(stock);
  };

  if (loading || !scan) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-text-muted text-sm tracking-wider uppercase">Loading dashboard...</div>
      </div>
    );
  }

  const scanDate = new Date(scan.timestamp);
  const now = new Date();
  const isToday = scanDate.toDateString() === now.toDateString();

  return (
    <motion.div variants={stagger} initial="hidden" animate="show" className="max-w-[1100px]">
      {/* Hero greeting */}
      <motion.div variants={fadeUp} className="mb-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold text-text-primary tracking-tight">
            {GREETING[tod]}, <span className="text-accent">Zhuoran</span>
          </h1>
          <button
            onClick={runScan}
            disabled={scanning}
            className="px-3 py-1.5 rounded-lg text-xs font-medium bg-accent/10 text-accent border border-accent/20 hover:bg-accent/20 transition-all disabled:opacity-60 flex items-center gap-1.5"
          >
            {scanning && <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />}
            {scanning ? "Scanning..." : "Run Scan"}
          </button>
        </div>
        <div className="flex items-center gap-3 mt-1.5">
          <span className="text-sm text-text-muted">
            {now.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" })}
          </span>
          <span className="w-1 h-1 rounded-full bg-border" />
          <span className={`text-sm ${isToday ? "text-text-secondary" : "text-caution"}`}>
            {isToday ? `Scanned ${scanDate.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}` : "Scan data is stale"}
          </span>
        </div>
      </motion.div>

      {/* Summary cards */}
      <motion.div variants={fadeUp}>
        <SummaryCards scan={scan} alerts={alerts} accuracy={accuracy} risk={risk} />
      </motion.div>

      {/* Holdings strip */}
      {stopLosses?.alerts && stopLosses.alerts.length > 0 && (
        <motion.div variants={fadeUp}>
          <HoldingsStrip alerts={stopLosses.alerts} onTickerClick={handleTickerClick} />
        </motion.div>
      )}

      {/* Main content grid */}
      <motion.div variants={fadeUp} className="grid grid-cols-3 gap-4">
        <ActionItems
          stopLosses={stopLosses?.alerts ?? []}
          earningsNear={scan.top.filter((s) => (s.sell_reasons ?? []).some((r) => r.toLowerCase().includes("earn")))}
          onTickerClick={handleTickerClick}
        />
        <NewSignals stocks={scan.top} onTickerClick={handleTickerClick} />
        <MarketPulse regime={scan.market_regime} />
      </motion.div>

      {selectedStock && <TickerModal stock={selectedStock} onClose={() => setSelectedStock(null)} />}
    </motion.div>
  );
}
