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

  return (
    <div className="rounded-xl bg-surface border border-border overflow-hidden">
      <div className="px-4 py-3 border-b border-border text-xs font-bold text-text-primary uppercase tracking-wider">
        Market Pulse
      </div>
      <div className="p-4 grid grid-cols-2 gap-2">
        <div>
          <div className="text-[11px] text-text-muted">SPY</div>
          <div className="text-sm font-semibold text-text-primary">${regime.spy_price.toFixed(2)}</div>
        </div>
        <div>
          <div className="text-[11px] text-text-muted">VIX</div>
          <div className={`text-sm font-semibold ${regime.macro.vix.current > regime.macro.vix.ma20 ? "text-danger" : "text-positive"}`}>
            {regime.macro.vix.current.toFixed(1)}
          </div>
        </div>
        <div>
          <div className="text-[11px] text-text-muted">10Y Rate</div>
          <div className="text-sm font-semibold text-caution">{regime.macro.us10y.current.toFixed(2)}%</div>
        </div>
        <div>
          <div className="text-[11px] text-text-muted">Regime</div>
          <div className={`text-sm font-semibold ${regimeColor}`}>
            {regime.regime.charAt(0).toUpperCase() + regime.regime.slice(1)}
          </div>
        </div>
      </div>
    </div>
  );
}
