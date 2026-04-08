import { useState, useCallback } from "react";
import { useApi } from "../hooks/useApi";
import { useScan } from "../App";
import { api } from "../lib/api";
import TickerModal from "../components/ticker/TickerModal";
import ScoreBadge from "../components/common/ScoreBadge";
import { pnlColor, scoreColor } from "../lib/colors";
import type { WatchlistResponse, Stock } from "../lib/types";

export default function Watchlist() {
  const { data, loading, refetch } = useApi<WatchlistResponse>(() => api.watchlist());
  const { scan } = useScan();
  const [selectedStock, setSelectedStock] = useState<Stock | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);

  const findStock = useCallback((ticker: string): Stock | null => {
    if (!scan) return null;
    return (
      scan.top.find((s) => s.ticker === ticker) ??
      scan.all_scores.find((s) => s.ticker === ticker) ??
      null
    );
  }, [scan]);

  const handleRemove = useCallback(async (e: React.MouseEvent, ticker: string) => {
    e.stopPropagation();
    setRemoving(ticker);
    try {
      await api.removeFromWatchlist(ticker);
      await refetch();
    } finally {
      setRemoving(null);
    }
  }, [refetch]);

  if (loading) {
    return <div className="text-text-secondary">Loading watchlist...</div>;
  }

  const entries = data ? Object.entries(data.tickers) : [];

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-bold">Watchlist</h1>
        <span className="text-xs text-text-muted">{entries.length} stocks</span>
      </div>

      {entries.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24 text-center">
          <span className="text-5xl mb-4 opacity-30">☆</span>
          <div className="text-text-secondary text-sm">Your watchlist is empty.</div>
          <div className="text-text-muted text-xs mt-1">Click the ☆ star next to any stock in the Scanner to add it here.</div>
        </div>
      ) : (
        <div className="rounded-xl border border-border overflow-hidden">
          <table className="w-full">
            <thead className="bg-surface">
              <tr>
                <th className="py-2.5 px-3 text-left text-[11px] text-text-muted uppercase tracking-wider font-semibold">Ticker</th>
                <th className="py-2.5 px-3 text-left text-[11px] text-text-muted uppercase tracking-wider font-semibold">Added</th>
                <th className="py-2.5 px-3 text-left text-[11px] text-text-muted uppercase tracking-wider font-semibold">Price Then</th>
                <th className="py-2.5 px-3 text-left text-[11px] text-text-muted uppercase tracking-wider font-semibold">Price Now</th>
                <th className="py-2.5 px-3 text-left text-[11px] text-text-muted uppercase tracking-wider font-semibold">Change</th>
                <th className="py-2.5 px-3 text-left text-[11px] text-text-muted uppercase tracking-wider font-semibold">Signal</th>
                <th className="py-2.5 px-3 text-left text-[11px] text-text-muted uppercase tracking-wider font-semibold">Score</th>
                <th className="py-2.5 px-3 text-left text-[11px] text-text-muted uppercase tracking-wider font-semibold"></th>
              </tr>
            </thead>
            <tbody>
              {entries.map(([ticker, entry]) => {
                const stock = findStock(ticker);
                const changePct = entry.change_pct ?? (
                  entry.price_at_add && entry.current_price
                    ? ((entry.current_price / entry.price_at_add - 1) * 100)
                    : null
                );
                return (
                  <tr
                    key={ticker}
                    onClick={() => stock && setSelectedStock(stock)}
                    className={`border-t border-surface transition-colors ${stock ? "cursor-pointer hover:bg-white/[0.03]" : ""}`}
                  >
                    <td className="py-2.5 px-3">
                      <div className="font-bold text-text-primary">{ticker}</div>
                      {stock && <div className="text-[11px] text-text-muted">{stock.name}</div>}
                    </td>
                    <td className="py-2.5 px-3 text-xs text-text-secondary font-data">
                      {entry.added ? entry.added.split("T")[0] : "—"}
                    </td>
                    <td className="py-2.5 px-3 text-sm font-data text-text-primary">
                      {entry.price_at_add ? `$${entry.price_at_add.toFixed(2)}` : "—"}
                    </td>
                    <td className="py-2.5 px-3 text-sm font-data text-text-primary">
                      {entry.current_price
                        ? `$${entry.current_price.toFixed(2)}`
                        : stock?.current_price
                        ? `$${stock.current_price.toFixed(2)}`
                        : "—"}
                    </td>
                    <td className="py-2.5 px-3 text-sm font-semibold font-data">
                      {changePct != null ? (
                        <span className={pnlColor(changePct)}>
                          {changePct >= 0 ? "+" : ""}{changePct.toFixed(2)}%
                        </span>
                      ) : "—"}
                    </td>
                    <td className="py-2.5 px-3">
                      {stock ? <ScoreBadge signal={stock.entry_signal} /> : <span className="text-text-muted text-xs">—</span>}
                    </td>
                    <td className="py-2.5 px-3">
                      {stock ? (
                        <span className={`text-lg font-bold font-data ${scoreColor(stock.composite_score)}`}>
                          {Math.round(stock.composite_score)}
                        </span>
                      ) : "—"}
                    </td>
                    <td className="py-2.5 px-3 text-right">
                      <button
                        onClick={(e) => handleRemove(e, ticker)}
                        disabled={removing === ticker}
                        className="text-xs text-text-muted/50 hover:text-danger transition-colors disabled:opacity-40"
                        title="Remove from watchlist"
                      >
                        {removing === ticker ? "…" : "✕"}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {selectedStock && (
        <TickerModal stock={selectedStock} onClose={() => setSelectedStock(null)} />
      )}
    </div>
  );
}
