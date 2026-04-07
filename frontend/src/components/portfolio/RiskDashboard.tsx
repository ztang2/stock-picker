import type { RiskSummary, MarketRegime } from "../../lib/types";
import SectorBar from "../common/SectorBar";
import MetricCard from "../common/MetricCard";

interface RiskDashboardProps {
  risk: RiskSummary;
  sectorWeights: Record<string, number>;
  regime: MarketRegime;
}

export default function RiskDashboard({ risk, sectorWeights, regime }: RiskDashboardProps) {
  const sortedSectors = Object.entries(sectorWeights).sort(([, a], [, b]) => b - a);

  return (
    <div>
      <div className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2.5">Risk Dashboard</div>
      <div className="p-4 rounded-xl bg-surface border border-border mb-3">
        <div className="text-xs font-semibold text-text-primary mb-3">Sector Exposure</div>
        {sortedSectors.map(([sector, pct]) => (
          <SectorBar key={sector} label={sector} pct={pct} />
        ))}
      </div>
      <div className="grid grid-cols-2 gap-2 mb-3">
        <MetricCard label="Win Rate" value={`${risk.win_rate?.toFixed(1) ?? "—"}%`} subtitle="Portfolio avg" />
        <MetricCard label="Positions" value={String(risk.num_positions ?? risk.stop_loss_alerts?.length ?? 0)} subtitle="Active holdings" />
      </div>
      <div className="p-3 rounded-lg bg-accent/5 border border-accent/15">
        <div className="text-[10px] text-text-muted uppercase tracking-wider mb-1.5">Macro Flags</div>
        <div className="flex flex-wrap gap-1.5">
          <span className={`px-2 py-0.5 rounded-full text-[11px] border ${
            regime.regime === "bull" ? "bg-positive/10 border-positive/20 text-positive" : "bg-danger/10 border-danger/20 text-danger"
          }`}>
            {regime.regime} regime
          </span>
          {(risk.concentration_warnings ?? []).map((w, i) => (
            <span key={i} className="px-2 py-0.5 rounded-full text-[11px] bg-caution/10 border border-caution/20 text-caution">
              {w}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
