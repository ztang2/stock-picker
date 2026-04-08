import { useState, useEffect, useCallback } from "react";
import { useScan } from "../App";
import { useApi } from "../hooks/useApi";
import { api } from "../lib/api";
import ScannerTable from "../components/scanner/ScannerTable";
import TickerModal from "../components/ticker/TickerModal";
import type { Stock, SnapshotDay, WatchlistResponse } from "../lib/types";

export default function Scanner() {
  const { scan, loading: scanLoading } = useScan();
  const { data: snapshots } = useApi<SnapshotDay[]>(() => api.snapshotsRecent(7));
  const [selectedStock, setSelectedStock] = useState<Stock | null>(null);
  const [watchedTickers, setWatchedTickers] = useState<Set<string>>(new Set());

  const fetchWatchlist = useCallback(async () => {
    try {
      const data = await api.watchlist() as WatchlistResponse;
      setWatchedTickers(new Set(Object.keys(data.tickers)));
    } catch {
      // silently ignore
    }
  }, []);

  useEffect(() => {
    fetchWatchlist();
  }, [fetchWatchlist]);

  const toggleWatch = useCallback(async (ticker: string) => {
    if (watchedTickers.has(ticker)) {
      await api.removeFromWatchlist(ticker);
      setWatchedTickers((prev) => {
        const next = new Set(prev);
        next.delete(ticker);
        return next;
      });
    } else {
      await api.addToWatchlist(ticker);
      setWatchedTickers((prev) => new Set(prev).add(ticker));
    }
  }, [watchedTickers]);

  if (scanLoading) {
    return <div className="text-text-secondary">Loading scan data...</div>;
  }

  if (!scan) {
    return <div className="text-text-secondary">No scan data available. Run a scan first.</div>;
  }

  const allStocks = [...scan.top, ...scan.all_scores.filter(
    (s) => !scan.top.some((t) => t.ticker === s.ticker)
  )].sort((a, b) => b.composite_score - a.composite_score);

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-bold">Scanner</h1>
        <span className="text-xs text-text-muted">{scan.stocks_analyzed} stocks analyzed</span>
      </div>
      <ScannerTable
        stocks={allStocks}
        snapshots={snapshots ?? []}
        onSelectStock={setSelectedStock}
        watchedTickers={watchedTickers}
        onToggleWatch={toggleWatch}
      />
      {selectedStock && (
        <TickerModal stock={selectedStock} onClose={() => setSelectedStock(null)} />
      )}
    </div>
  );
}
