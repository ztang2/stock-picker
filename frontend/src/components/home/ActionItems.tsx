import type { StopLossAlert, Stock } from "../../lib/types";
import ActionBadge from "../common/ActionBadge";

interface ActionItem {
  ticker: string;
  priority: "urgent" | "review" | "watch";
  title: string;
  subtitle: string;
}

interface ActionItemsProps {
  stopLosses: StopLossAlert[];
  earningsNear: Stock[];
  onTickerClick?: (ticker: string) => void;
}

export default function ActionItems({ stopLosses, earningsNear, onTickerClick }: ActionItemsProps) {
  const items: ActionItem[] = [];

  for (const sl of stopLosses) {
    if ((sl.pnl_pct ?? 0) < -10) {
      items.push({
        ticker: sl.ticker,
        priority: "urgent",
        title: `${Math.abs(sl.pnl_pct ?? 0).toFixed(1)}% loss — ${sl.status === "TRIGGERED" ? "stop triggered" : "near stop"}`,
        subtitle: `Current: $${sl.current_price?.toFixed(2) ?? "—"} · Entry: $${sl.entry_price?.toFixed(2) ?? "—"}`,
      });
    }
  }

  for (const stock of earningsNear) {
    items.push({
      ticker: stock.ticker,
      priority: "watch",
      title: "Earnings approaching",
      subtitle: (stock.sell_reasons ?? []).find((r) => r.toLowerCase().includes("earn")) ?? "Check earnings date",
    });
  }

  return (
    <div className="rounded-lg bg-surface border border-border overflow-hidden">
      <div className="px-4 py-3 border-b border-border flex items-center justify-between">
        <div className="flex items-center gap-2">
          {items.some((i) => i.priority === "urgent") && (
            <div className="w-1.5 h-1.5 rounded-full bg-danger animate-pulse-dot" />
          )}
          <span className="text-[10px] font-semibold text-text-muted uppercase tracking-widest">
            Action Items
          </span>
        </div>
        <span className="text-[10px] font-data text-text-muted">{items.length}</span>
      </div>
      {items.length === 0 ? (
        <div className="px-4 py-3 text-xs text-text-muted">All clear</div>
      ) : (
        items.map((item, i) => (
          <div
            key={`${item.ticker}-${i}`}
            onClick={() => onTickerClick?.(item.ticker)}
            className="px-4 py-3 border-b border-border/40 last:border-0 flex items-center gap-3 hover:bg-accent/[0.05] cursor-pointer transition-colors"
          >
            <ActionBadge priority={item.priority} />
            <div className="flex-1 min-w-0">
              <div className="text-[13px] text-text-primary font-medium">
                <span className="font-semibold">{item.ticker}</span>
                <span className="text-text-secondary ml-1.5">— {item.title}</span>
              </div>
              <div className="text-[11px] text-text-muted mt-0.5 truncate">{item.subtitle}</div>
            </div>
          </div>
        ))
      )}
    </div>
  );
}
