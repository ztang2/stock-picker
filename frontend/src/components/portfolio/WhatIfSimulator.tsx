import { useState } from "react";
import { useApi } from "../../hooks/useApi";
import { api } from "../../lib/api";
import type { WhatIfResponse } from "../../lib/types";
import { pnlColor } from "../../lib/colors";

export default function WhatIfSimulator() {
  const [ticker, setTicker] = useState("");
  const [submitted, setSubmitted] = useState("");
  const { data, loading } = useApi<WhatIfResponse>(
    () => submitted ? api.whatIf(submitted) : Promise.resolve(null as unknown as WhatIfResponse),
    [submitted]
  );

  return (
    <div className="p-4 rounded-xl bg-surface border border-border">
      <div className="text-xs font-semibold text-text-primary mb-3">What If Simulator</div>
      <div className="flex gap-2 mb-3">
        <input
          value={ticker}
          onChange={(e) => setTicker(e.target.value.toUpperCase())}
          onKeyDown={(e) => e.key === "Enter" && setSubmitted(ticker)}
          placeholder="Enter ticker..."
          className="flex-1 px-3 py-1.5 rounded-md bg-base border border-border text-sm text-text-primary placeholder:text-text-muted"
        />
        <button
          onClick={() => setSubmitted(ticker)}
          className="px-4 py-1.5 rounded-md bg-accent text-white text-xs font-semibold"
        >
          Analyze
        </button>
      </div>
      {loading && submitted && <div className="text-xs text-text-secondary">Analyzing impact...</div>}
      {data && !loading && (
        <div className="space-y-2">
          <div className="flex justify-between text-xs">
            <span className="text-text-secondary">Sector</span>
            <span className="text-text-primary font-semibold">{data.sector}</span>
          </div>
          <div className="flex justify-between text-xs">
            <span className="text-text-secondary">Diversification</span>
            <span className={pnlColor(data.diversification_after - data.diversification_before)}>
              {data.diversification_before.toFixed(0)} → {data.diversification_after.toFixed(0)}
            </span>
          </div>
          <div className="flex justify-between text-xs">
            <span className="text-text-secondary">Beta</span>
            <span className="text-text-primary">{data.beta_before.toFixed(2)} → {data.beta_after.toFixed(2)}</span>
          </div>
          {Object.entries(data.correlation_with_holdings).length > 0 && (
            <div>
              <div className="text-[10px] text-text-muted uppercase mt-2 mb-1">Correlation with Holdings</div>
              {Object.entries(data.correlation_with_holdings).map(([t, c]) => (
                <div key={t} className="flex justify-between text-xs">
                  <span className="text-text-secondary">{t}</span>
                  <span className={c > 0.7 ? "text-danger" : c > 0.4 ? "text-caution" : "text-positive"}>{c.toFixed(3)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
