import { useScan } from "../App";
import { useApi } from "../hooks/useApi";
import { api } from "../lib/api";
import HoldingCard from "../components/portfolio/HoldingCard";
import RiskDashboard from "../components/portfolio/RiskDashboard";
import DiversificationScore from "../components/portfolio/DiversificationScore";
import CorrelationHeatmap from "../components/portfolio/CorrelationHeatmap";
import WhatIfSimulator from "../components/portfolio/WhatIfSimulator";
import RebalanceSuggestions from "../components/portfolio/RebalanceSuggestions";
import type { RiskSummary, DiversificationResponse, CorrelationResponse } from "../lib/types";
import { pnlColor } from "../lib/colors";

export default function Portfolio() {
  const { scan } = useScan();
  const { data: risk } = useApi<RiskSummary>(() => api.riskSummary());
const { data: diversification } = useApi<DiversificationResponse>(() => api.diversification());
  const { data: correlation } = useApi<CorrelationResponse>(() => api.correlation());

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

      <div className="grid grid-cols-[1.4fr_1fr] gap-4 mb-6">
        <div>
          <div className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2.5">Holdings</div>
          <div className="flex flex-col gap-2">
            {positions.map((p) => (
              <HoldingCard
                key={p.ticker}
                position={p}
                signal={tickerSignal[p.ticker]}
                stopLossPct={p.stop_loss_threshold ?? -15}
                profitTriggered={false}
                totalValue={portfolioValue}
              />
            ))}
          </div>
        </div>
        <RiskDashboard risk={risk} sectorWeights={sectorWeights} regime={scan.market_regime} />
      </div>

      <div className="grid grid-cols-2 gap-4 mb-4">
        {diversification && <DiversificationScore data={diversification} />}
        {correlation && <CorrelationHeatmap data={correlation} />}
      </div>
      <div className="grid grid-cols-2 gap-4">
        <WhatIfSimulator />
        {diversification && <RebalanceSuggestions data={diversification} />}
      </div>
    </div>
  );
}
