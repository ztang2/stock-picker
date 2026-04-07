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
}

export default function ActionItems({ stopLosses, earningsNear }: ActionItemsProps) {
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
      subtitle: stock.sell_reasons.find((r) => r.toLowerCase().includes("earn")) ?? "Check earnings date",
    });
  }

  if (items.length === 0) {
    return (
      <div className="rounded-xl bg-surface border border-border p-4 text-sm text-text-secondary">
        No action items today
      </div>
    );
  }

  return (
    <div className="rounded-xl bg-surface border border-border overflow-hidden">
      <div className="px-4 py-3 border-b border-border flex items-center gap-2">
        {items.some((i) => i.priority === "urgent") && (
          <div className="w-2 h-2 rounded-full bg-danger animate-pulse-dot" />
        )}
        <span className="text-xs font-bold text-text-primary uppercase tracking-wider">
          {items.length} Action{items.length > 1 ? "s" : ""} Needed
        </span>
      </div>
      {items.map((item, i) => (
        <div
          key={`${item.ticker}-${i}`}
          className="px-4 py-3 border-b border-border/50 last:border-0 flex items-center gap-3 hover:bg-accent/5 cursor-pointer transition-colors"
        >
          <ActionBadge priority={item.priority} />
          <div className="flex-1">
            <div className="text-[13px] text-text-primary font-semibold">{item.ticker} — {item.title}</div>
            <div className="text-xs text-text-secondary">{item.subtitle}</div>
          </div>
        </div>
      ))}
    </div>
  );
}
