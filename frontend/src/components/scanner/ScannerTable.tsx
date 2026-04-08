import { useState, useMemo } from "react";
import type { Stock, SnapshotDay } from "../../lib/types";
import ScannerRow from "./ScannerRow";
import SectorFilter from "./SectorFilter";

interface ScannerTableProps {
  stocks: Stock[];
  snapshots: SnapshotDay[];
  onSelectStock: (stock: Stock) => void;
  watchedTickers?: Set<string>;
  onToggleWatch?: (ticker: string) => void;
}

export default function ScannerTable({ stocks, snapshots, onSelectStock, watchedTickers, onToggleWatch }: ScannerTableProps) {
  const [sectorFilter, setSectorFilter] = useState<string | null>(null);
  const [signalFilter, setSignalFilter] = useState<string | null>(null);
  const [sortCol, setSortCol] = useState<string>("composite_score");
  const [sortAsc, setSortAsc] = useState(false);

  const sectors = useMemo(() => {
    const s = new Set(stocks.map((st) => st.sector));
    return Array.from(s).sort();
  }, [stocks]);

  const filtered = useMemo(() => {
    let result = stocks;
    if (sectorFilter) result = result.filter((s) => s.sector === sectorFilter);
    if (signalFilter) result = result.filter((s) => s.entry_signal === signalFilter);
    result = [...result].sort((a, b) => {
      const av = ((a as unknown) as Record<string, unknown>)[sortCol] as number;
      const bv = ((b as unknown) as Record<string, unknown>)[sortCol] as number;
      return sortAsc ? av - bv : bv - av;
    });
    return result;
  }, [stocks, sectorFilter, signalFilter, sortCol, sortAsc]);

  function getSparkline(ticker: string): number[] {
    return snapshots.map((snap) => snap.stocks[ticker]?.composite_score ?? 0);
  }

  function getScoreDelta(ticker: string): number | null {
    if (snapshots.length < 2) return null;
    const prev = snapshots[snapshots.length - 2]?.stocks[ticker]?.composite_score;
    const curr = snapshots[snapshots.length - 1]?.stocks[ticker]?.composite_score;
    if (prev == null || curr == null) return null;
    return Math.round(curr - prev);
  }

  function toggleSort(col: string) {
    if (sortCol === col) setSortAsc(!sortAsc);
    else { setSortCol(col); setSortAsc(false); }
  }

  const TH = ({ col, children }: { col: string; children: React.ReactNode }) => (
    <th
      onClick={() => toggleSort(col)}
      className="py-2.5 px-3 text-left text-[11px] text-text-muted uppercase tracking-wider font-semibold cursor-pointer hover:text-text-primary"
    >
      {children} {sortCol === col ? (sortAsc ? "↑" : "↓") : ""}
    </th>
  );

  return (
    <div>
      <SectorFilter
        sectors={sectors}
        active={sectorFilter}
        onSelect={setSectorFilter}
        signalFilter={signalFilter}
        onSignalChange={setSignalFilter}
      />
      <div className="rounded-lg border border-border overflow-hidden overflow-x-auto">
        <table className="w-full min-w-[700px]">
          <thead className="bg-surface">
            <tr>
              <th className="py-2.5 px-1.5 w-8"></th>
              <TH col="rank">#</TH>
              <TH col="ticker">Ticker</TH>
              <th className="py-2.5 px-3 text-left text-[11px] text-text-muted uppercase tracking-wider font-semibold">Profile</th>
              <TH col="composite_score">Score</TH>
              <th className="py-2.5 px-3 text-left text-[11px] text-text-muted uppercase tracking-wider font-semibold">7d Trend</th>
              <TH col="entry_signal">Signal</TH>
              <TH col="current_price">Price</TH>
              <th className="py-2.5 px-3 text-left text-[11px] text-text-muted uppercase tracking-wider font-semibold">vs MA50</th>
              <TH col="consecutive_days">Streak</TH>
            </tr>
          </thead>
          <tbody>
            {filtered.map((stock, i) => (
              <ScannerRow
                key={stock.ticker}
                stock={stock}
                rank={i + 1}
                sparkline={getSparkline(stock.ticker)}
                scoreDelta={getScoreDelta(stock.ticker)}
                onClick={() => onSelectStock(stock)}
                isWatched={watchedTickers?.has(stock.ticker)}
                onToggleWatch={onToggleWatch}
              />
            ))}
          </tbody>
        </table>
        <div className="py-2.5 px-3 text-center text-xs text-text-muted border-t border-border">
          Showing {filtered.length} of {stocks.length} stocks
        </div>
      </div>
    </div>
  );
}
