import { useState, useEffect } from "react";
import { api } from "../../lib/api";
import type { RiskSummary } from "../../lib/types";

interface PositionSizerProps {
  ticker: string;
  currentPrice: number;
}

export default function PositionSizer({ ticker: _ticker, currentPrice }: PositionSizerProps) {
  const [riskPct, setRiskPct] = useState(() => {
    const saved = localStorage.getItem("positionSizer_riskPct");
    return saved ? parseFloat(saved) : 2;
  });
  const [portfolioValue, setPortfolioValue] = useState<number | null>(null);
  const stopLossPct = 15;

  useEffect(() => {
    api.riskSummary().then((r: RiskSummary) => setPortfolioValue(r.portfolio_value ?? 0)).catch(() => {});
  }, []);

  useEffect(() => {
    localStorage.setItem("positionSizer_riskPct", String(riskPct));
  }, [riskPct]);

  if (!portfolioValue || currentPrice <= 0) return null;

  const riskPerTrade = portfolioValue * (riskPct / 100);
  const stopDistance = currentPrice * (stopLossPct / 100);
  const shares = Math.floor(riskPerTrade / stopDistance);
  const dollarAmount = shares * currentPrice;
  const weightPct = (dollarAmount / portfolioValue) * 100;
  const stopPrice = currentPrice * (1 - stopLossPct / 100);

  return (
    <div className="rounded-xl bg-surface border border-border p-4 mb-4">
      <div className="flex justify-between items-center mb-3">
        <span className="text-xs font-semibold text-text-muted uppercase tracking-wider">Position Sizer</span>
        <div className="flex items-center gap-2">
          <span className="text-[11px] text-text-muted">Risk:</span>
          <input
            type="range"
            min={0.5}
            max={5}
            step={0.5}
            value={riskPct}
            onChange={(e) => setRiskPct(parseFloat(e.target.value))}
            className="w-20 h-1 accent-accent"
          />
          <span className="text-xs font-data text-accent font-semibold w-8">{riskPct}%</span>
        </div>
      </div>
      <div className="grid grid-cols-4 gap-3">
        <div>
          <div className="text-[11px] text-text-muted">Shares</div>
          <div className="text-lg font-bold text-text-primary font-data">{shares}</div>
        </div>
        <div>
          <div className="text-[11px] text-text-muted">Amount</div>
          <div className="text-lg font-bold text-text-primary font-data">${dollarAmount.toLocaleString()}</div>
        </div>
        <div>
          <div className="text-[11px] text-text-muted">Weight</div>
          <div className="text-lg font-bold text-text-primary font-data">{weightPct.toFixed(1)}%</div>
        </div>
        <div>
          <div className="text-[11px] text-text-muted">Stop at</div>
          <div className="text-lg font-bold text-danger font-data">${stopPrice.toFixed(2)}</div>
        </div>
      </div>
      <div className="text-[11px] text-text-muted mt-2">
        Risking ${riskPerTrade.toFixed(0)} ({riskPct}% of ${portfolioValue.toLocaleString()}) with {stopLossPct}% stop-loss
      </div>
    </div>
  );
}
