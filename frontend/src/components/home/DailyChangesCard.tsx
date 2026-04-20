import { useApi } from "../../hooks/useApi";
import { api, type ChangeEntry, type ScanChangesResponse } from "../../lib/api";
import { TrendingUp, TrendingDown, ArrowRight, Plus, X } from "lucide-react";

interface Props {
  onTickerClick?: (ticker: string) => void;
  daysBack?: number;
}

const SIGNAL_RANK: Record<string, number> = {
  STRONG_BUY: 0,
  BUY: 1,
  HOLD: 2,
  WAIT: 3,
  AVOID: 4,
};

function signalChangeColor(prev?: string, cur?: string): string {
  if (!prev || !cur) return "text-text-muted";
  const p = SIGNAL_RANK[prev.toUpperCase()];
  const c = SIGNAL_RANK[cur.toUpperCase()];
  if (p === undefined || c === undefined) return "text-text-muted";
  if (c < p) return "text-positive";
  if (c > p) return "text-danger";
  return "text-text-muted";
}

export default function DailyChangesCard({ onTickerClick, daysBack = 1 }: Props) {
  const { data, loading } = useApi<ScanChangesResponse>(() => api.scanChanges(daysBack));
  if (loading) return null;
  if (!data || data.error) return null;

  const { held_changes, top_risers, top_fallers, new_in_top, dropped_from_top, summary, current_date, previous_date, days_back } = data;

  // If literally nothing changed, show a quiet placeholder rather than an empty card
  const nothingChanged = summary.held_changed === 0 && summary.new_in_top === 0 &&
    summary.dropped_from_top === 0 && top_risers.length === 0 && top_fallers.length === 0;

  return (
    <div className="rounded-xl bg-surface border border-border p-4 md:col-span-2 lg:col-span-3">
      <div className="flex items-baseline justify-between mb-3">
        <h3 className="text-sm font-semibold text-text-muted uppercase tracking-wider">
          What Changed <span className="text-text-muted/70 font-normal">({days_back}d)</span>
        </h3>
        <div className="text-[11px] text-text-muted font-data">
          {previous_date} <ArrowRight size={10} className="inline mb-0.5" /> {current_date}
        </div>
      </div>

      {nothingChanged ? (
        <div className="text-sm text-text-secondary py-4 text-center">
          No material changes since {previous_date}.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-4">
          {/* Held position changes — full width on top */}
          {held_changes.length > 0 && (
            <Section title="Your Holdings" count={held_changes.length} className="md:col-span-2">
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2">
                {held_changes.map((c) => (
                  <HoldingDelta key={c.ticker} change={c} onClick={onTickerClick} />
                ))}
              </div>
            </Section>
          )}

          {/* Top movers */}
          {top_risers.length > 0 && (
            <Section title="Top Risers" count={top_risers.length} icon={<TrendingUp size={13} className="text-positive" strokeWidth={2.5} />}>
              <MoverList movers={top_risers} positive onClick={onTickerClick} />
            </Section>
          )}
          {top_fallers.length > 0 && (
            <Section title="Top Fallers" count={top_fallers.length} icon={<TrendingDown size={13} className="text-danger" strokeWidth={2.5} />}>
              <MoverList movers={top_fallers} positive={false} onClick={onTickerClick} />
            </Section>
          )}

          {/* Top 20 churn */}
          {new_in_top.length > 0 && (
            <Section title="New in Top 20" count={new_in_top.length} icon={<Plus size={13} className="text-accent" strokeWidth={2.5} />}>
              <NewDropList items={new_in_top} kind="new" onClick={onTickerClick} />
            </Section>
          )}
          {dropped_from_top.length > 0 && (
            <Section title="Dropped from Top 20" count={dropped_from_top.length} icon={<X size={13} className="text-text-muted" strokeWidth={2.5} />}>
              <NewDropList items={dropped_from_top} kind="dropped" onClick={onTickerClick} />
            </Section>
          )}
        </div>
      )}
    </div>
  );
}

function Section({ title, count, children, icon, className }: { title: string; count: number; children: React.ReactNode; icon?: React.ReactNode; className?: string }) {
  return (
    <div className={className}>
      <div className="flex items-center gap-1.5 mb-2 text-[11px] font-semibold text-text-muted uppercase tracking-wider">
        {icon}
        <span>{title}</span>
        <span className="text-text-muted/60 normal-case font-normal">· {count}</span>
      </div>
      {children}
    </div>
  );
}

function HoldingDelta({ change, onClick }: { change: ChangeEntry; onClick?: (t: string) => void }) {
  const sigColor = signalChangeColor(change.previous_signal, change.current_signal);
  const rd = change.rank_delta ?? 0;
  const sd = change.score_delta ?? 0;
  return (
    <button
      type="button"
      onClick={() => onClick?.(change.ticker)}
      className="text-left p-2.5 rounded-lg bg-base/40 border border-border-subtle hover:border-accent/40 transition-colors"
    >
      <div className="flex items-baseline justify-between mb-1">
        <span className="text-sm font-bold text-text-primary">{change.ticker}</span>
        {change.signal_changed && (
          <span className={`text-[10px] font-mono ${sigColor}`}>
            {change.previous_signal}→{change.current_signal}
          </span>
        )}
      </div>
      <div className="flex items-center justify-between text-[11px] font-data">
        <span className="text-text-muted">
          rank{" "}
          <span className={rd > 0 ? "text-positive" : rd < 0 ? "text-danger" : "text-text-secondary"}>
            #{change.previous_rank} → #{change.current_rank}
            {rd !== 0 && ` (${rd > 0 ? "+" : ""}${rd})`}
          </span>
        </span>
        <span className={sd > 0 ? "text-positive" : sd < 0 ? "text-danger" : "text-text-muted"}>
          {sd > 0 ? "+" : ""}{sd.toFixed(1)}pts
        </span>
      </div>
    </button>
  );
}

function MoverList({ movers, positive, onClick }: { movers: ChangeEntry[]; positive: boolean; onClick?: (t: string) => void }) {
  return (
    <div className="space-y-1">
      {movers.map((m) => (
        <button
          key={m.ticker}
          type="button"
          onClick={() => onClick?.(m.ticker)}
          className="w-full flex items-center justify-between px-2.5 py-1.5 rounded-md hover:bg-base/40 transition-colors text-left"
        >
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-[13px] font-bold text-text-primary">{m.ticker}</span>
            <span className="text-[10px] text-text-muted truncate">{m.sector}</span>
          </div>
          <div className="flex items-baseline gap-2 font-data text-[11px]">
            <span className="text-text-muted">#{m.previous_rank}→#{m.current_rank}</span>
            <span className={positive ? "text-positive font-semibold" : "text-danger font-semibold"}>
              {(m.score_delta ?? 0) > 0 ? "+" : ""}{(m.score_delta ?? 0).toFixed(1)}
            </span>
          </div>
        </button>
      ))}
    </div>
  );
}

function NewDropList({ items, kind, onClick }: { items: ChangeEntry[]; kind: "new" | "dropped"; onClick?: (t: string) => void }) {
  return (
    <div className="space-y-1">
      {items.map((m) => (
        <button
          key={m.ticker}
          type="button"
          onClick={() => onClick?.(m.ticker)}
          className="w-full flex items-center justify-between px-2.5 py-1.5 rounded-md hover:bg-base/40 transition-colors text-left"
        >
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-[13px] font-bold text-text-primary">{m.ticker}</span>
            <span className="text-[10px] text-text-muted truncate">{m.sector}</span>
          </div>
          <div className="font-data text-[11px] text-text-muted">
            {kind === "new"
              ? <>now #{m.current_rank} · {m.current_score?.toFixed(1)}</>
              : <>was #{m.previous_rank} → now #{m.current_rank ?? "—"}</>}
          </div>
        </button>
      ))}
    </div>
  );
}
