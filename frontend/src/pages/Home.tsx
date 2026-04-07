import { motion } from "framer-motion";
import { useScan } from "../App";
import { useApi } from "../hooks/useApi";
import { useTimeOfDay } from "../hooks/useTimeOfDay";
import { api } from "../lib/api";
import SummaryCards from "../components/home/SummaryCards";
import ActionItems from "../components/home/ActionItems";
import NewSignals from "../components/home/NewSignals";
import MarketPulse from "../components/home/MarketPulse";
import type { AlertsResponse, AccuracyResponse, RiskSummary, StopLossAlert } from "../lib/types";

const GREETING: Record<string, string> = {
  morning: "Good morning",
  midday: "Good afternoon",
  evening: "Good evening",
};

const stagger = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.08 } },
};

const fadeUp = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { duration: 0.4, ease: "easeOut" as const } },
};

export default function Home() {
  const { scan, loading } = useScan();
  const tod = useTimeOfDay();
  const { data: alerts } = useApi<AlertsResponse>(() => api.alerts());
  const { data: accuracy } = useApi<AccuracyResponse>(() => api.accuracy());
  const { data: risk } = useApi<RiskSummary>(() => api.riskSummary());
  const { data: stopLosses } = useApi<{ alerts: StopLossAlert[] }>(() => api.stopLosses());

  if (loading || !scan) {
    return <div className="text-text-secondary">Loading...</div>;
  }

  return (
    <motion.div variants={stagger} initial="hidden" animate="show">
      <motion.div variants={fadeUp} className="flex justify-between items-center mb-5">
        <div>
          <h1 className="text-xl font-bold text-text-primary">{GREETING[tod]}, Zhuoran</h1>
          <div className="text-[13px] text-text-secondary">
            {new Date().toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" })}
            {" · "}Last scan: {new Date(scan.timestamp).toLocaleTimeString()}
          </div>
        </div>
      </motion.div>

      <motion.div variants={fadeUp}>
        <SummaryCards scan={scan} alerts={alerts} accuracy={accuracy} risk={risk} />
      </motion.div>

      <motion.div variants={fadeUp} className="grid grid-cols-[1.2fr_1fr] gap-4">
        <ActionItems
          stopLosses={stopLosses?.alerts ?? []}
          earningsNear={scan.top.filter((s) => (s.sell_reasons ?? []).some((r) => r.toLowerCase().includes("earn")))}
        />
        <div className="flex flex-col gap-4">
          <NewSignals stocks={scan.top} />
          <MarketPulse regime={scan.market_regime} />
        </div>
      </motion.div>
    </motion.div>
  );
}
