import type { MarketRegime } from "../../lib/types";

interface MarketPulseProps {
  regime: MarketRegime;
}

export default function MarketPulse({ regime }: MarketPulseProps) {
  const regimeColor = {
    bull: "text-positive",
    bear: "text-danger",
    sideways: "text-caution",
  }[regime.regime];

  const regimeLabel = regime.regime.charAt(0).toUpperCase() + regime.regime.slice(1);

  return (
    <div className="rounded-lg bg-surface border border-border overflow-hidden">
      <div className="px-4 py-3 border-b border-border flex items-center justify-between">
        <span className="text-[10px] font-semibold text-text-muted uppercase tracking-widest">Market Pulse</span>
        <span className={`text-xs font-semibold ${regimeColor}`}>{regimeLabel}</span>
      </div>
      <div className="p-4 grid grid-cols-3 gap-4">
        <div>
          <div className="text-[10px] text-text-muted uppercase tracking-wider">SPY</div>
          <div className="text-sm font-semibold text-text-primary font-data mt-0.5">
            {regime.spy_price != null ? `$${regime.spy_price.toFixed(2)}` : "—"}
          </div>
        </div>
        <div>
          <div className="text-[10px] text-text-muted uppercase tracking-wider">VIX</div>
          <div className={`text-sm font-semibold font-data mt-0.5 ${(regime.macro?.vix?.current ?? 0) > (regime.macro?.vix?.ma20 ?? 0) ? "text-danger" : "text-positive"}`}>
            {regime.macro?.vix?.current?.toFixed(1) ?? "—"}
          </div>
        </div>
        <div>
          <div className="text-[10px] text-text-muted uppercase tracking-wider">10Y</div>
          <div className="text-sm font-semibold text-text-primary font-data mt-0.5">
            {regime.macro?.us10y?.current?.toFixed(2) ?? "—"}%
          </div>
        </div>
      </div>
    </div>
  );
}
