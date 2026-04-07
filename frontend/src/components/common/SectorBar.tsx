interface SectorBarProps {
  label: string;
  pct: number;
  warnThreshold?: number;
}

export default function SectorBar({ label, pct, warnThreshold = 35 }: SectorBarProps) {
  const isOver = pct >= warnThreshold;

  return (
    <div className="mb-2">
      <div className="flex justify-between text-xs mb-1">
        <span className="text-text-secondary">{label}</span>
        <span className={`font-semibold ${isOver ? "text-caution" : "text-positive"}`}>
          {pct.toFixed(0)}%{isOver ? " ⚠️" : ""}
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-border overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${isOver ? "bg-gradient-to-r from-accent to-caution" : "bg-accent"}`}
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
      </div>
    </div>
  );
}
