import { useState } from "react";
import { Plus } from "lucide-react";
import { useScan } from "../App";
import { useApi } from "../hooks/useApi";
import { api, type HoldingRecord } from "../lib/api";
import HoldingCard from "../components/portfolio/HoldingCard";
import HoldingFormModal from "../components/portfolio/HoldingFormModal";
import SellModal from "../components/portfolio/SellModal";
import AddSharesModal from "../components/portfolio/AddSharesModal";
import RiskDashboard from "../components/portfolio/RiskDashboard";
import DiversificationScore from "../components/portfolio/DiversificationScore";
import CorrelationHeatmap from "../components/portfolio/CorrelationHeatmap";
import WhatIfSimulator from "../components/portfolio/WhatIfSimulator";
import RebalanceSuggestions from "../components/portfolio/RebalanceSuggestions";
import type { RiskSummary, DiversificationResponse, CorrelationResponse } from "../lib/types";
import { pnlColor } from "../lib/colors";

type ModalState = { open: boolean; mode: "add" | "edit"; ticker?: string };

export default function Portfolio() {
  const { scan, refetch: refetchScan } = useScan();
  const { data: risk, refetch: refetchRisk } = useApi<RiskSummary>(() => api.riskSummary());
  const { data: diversification, refetch: refetchDiv } = useApi<DiversificationResponse>(() => api.diversification());
  const { data: correlation, refetch: refetchCorr } = useApi<CorrelationResponse>(() => api.correlation());
  const { data: holdings, refetch: refetchHoldings } = useApi<{ holdings: Record<string, HoldingRecord> }>(() => api.listHoldings());

  const [modal, setModal] = useState<ModalState>({ open: false, mode: "add" });
  const [sellTicker, setSellTicker] = useState<string | null>(null);
  const [addSharesTicker, setAddSharesTicker] = useState<string | null>(null);

  if (!risk || !scan) return <div className="text-text-secondary">Loading portfolio...</div>;

  const positions = risk.stop_loss_alerts ?? [];
  const portfolioValue = risk.portfolio_value ?? 0;

  const sectorWeights: Record<string, number> = {};
  const tickerSignal: Record<string, string> = {};
  for (const s of [...scan.top, ...scan.all_scores]) {
    tickerSignal[s.ticker] = s.entry_signal;
  }
  for (const p of positions) {
    const stock = [...scan.top, ...scan.all_scores].find((s) => s.ticker === p.ticker);
    const sector = stock?.sector ?? "Unknown";
    const posValue = (p.shares ?? 0) * (p.current_price ?? 0);
    const weight = portfolioValue > 0 ? (posValue / portfolioValue) * 100 : 0;
    sectorWeights[sector] = (sectorWeights[sector] ?? 0) + weight;
  }

  const editInitial =
    modal.mode === "edit" && modal.ticker && holdings?.holdings?.[modal.ticker]
      ? { ticker: modal.ticker, ...holdings.holdings[modal.ticker] }
      : null;

  function refetchAll() {
    refetchHoldings();
    refetchRisk();
    refetchDiv();
    refetchCorr();
    refetchScan();
  }

  const sellHolding = sellTicker ? holdings?.holdings?.[sellTicker] ?? null : null;
  const sellCurrentPrice = sellTicker
    ? positions.find((p) => p.ticker === sellTicker)?.current_price
    : undefined;

  const addSharesHolding = addSharesTicker ? holdings?.holdings?.[addSharesTicker] ?? null : null;
  const addSharesCurrentPrice = addSharesTicker
    ? positions.find((p) => p.ticker === addSharesTicker)?.current_price
    : undefined;

  return (
    <div>
      <div className="flex items-end justify-between mb-5">
        <div>
          <div className="text-[13px] text-text-muted mb-1">Total Portfolio Value</div>
          <div className="flex items-baseline gap-3">
            <span className="text-4xl font-extrabold text-text-primary">
              ${portfolioValue.toLocaleString()}
            </span>
            <span className={`text-base font-semibold ${pnlColor(risk.total_pnl ?? 0)}`}>
              {(risk.total_pnl ?? 0) >= 0 ? "+" : ""}${(risk.total_pnl ?? 0).toLocaleString()} ({(risk.total_pnl_pct ?? 0).toFixed(2)}%)
            </span>
          </div>
          <div className="text-[13px] text-text-secondary mt-1">
            {positions.length} positions · {Object.keys(sectorWeights).length} sectors
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1.4fr_1fr] gap-4 mb-6">
        <div>
          <div className="flex items-center justify-between mb-2.5">
            <div className="text-xs font-semibold text-text-muted uppercase tracking-wider">Holdings</div>
            <button
              type="button"
              onClick={() => setModal({ open: true, mode: "add" })}
              className="flex items-center gap-1 px-2.5 py-1 rounded-md border border-border text-xs text-text-secondary hover:text-accent hover:border-accent/50 transition-colors"
            >
              <Plus size={13} strokeWidth={2.5} />
              <span>Add Holding</span>
            </button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-1 gap-2">
            {[...positions].sort((a, b) => (b.shares ?? 0) * (b.current_price ?? 0) - (a.shares ?? 0) * (a.current_price ?? 0)).map((p) => (
              <HoldingCard
                key={p.ticker}
                position={p}
                signal={tickerSignal[p.ticker]}
                stopLossPct={p.stop_loss_threshold ?? -15}
                profitTriggered={false}
                totalValue={portfolioValue}
                onEdit={(t) => setModal({ open: true, mode: "edit", ticker: t })}
                onRemove={(t) => setSellTicker(t)}
                onAddShares={(t) => setAddSharesTicker(t)}
              />
            ))}
          </div>
        </div>
        {scan.market_regime && <RiskDashboard risk={risk} sectorWeights={sectorWeights} regime={scan.market_regime} />}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
        {diversification && <DiversificationScore data={diversification} />}
        {correlation && <CorrelationHeatmap data={correlation} />}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <WhatIfSimulator />
        {diversification && <RebalanceSuggestions data={diversification} />}
      </div>

      <HoldingFormModal
        open={modal.open}
        mode={modal.mode}
        initial={editInitial}
        onClose={() => setModal({ open: false, mode: "add" })}
        onSaved={refetchAll}
      />

      <SellModal
        open={!!sellTicker}
        ticker={sellTicker}
        holding={sellHolding}
        currentPrice={sellCurrentPrice}
        onClose={() => setSellTicker(null)}
        onSaved={refetchAll}
      />

      <AddSharesModal
        open={!!addSharesTicker}
        ticker={addSharesTicker}
        holding={addSharesHolding}
        currentPrice={addSharesCurrentPrice}
        onClose={() => setAddSharesTicker(null)}
        onSaved={refetchAll}
      />
    </div>
  );
}
