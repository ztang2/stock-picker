interface SectorFilterProps {
  sectors: string[];
  active: string | null;
  onSelect: (sector: string | null) => void;
  signalFilter: string | null;
  onSignalChange: (signal: string | null) => void;
}

const SIGNALS = ["STRONG_BUY", "BUY", "HOLD", "WAIT"];

export default function SectorFilter({ sectors, active, onSelect, signalFilter, onSignalChange }: SectorFilterProps) {
  return (
    <div className="flex items-center gap-2 flex-wrap mb-4">
      <button
        onClick={() => onSelect(null)}
        className={`px-3.5 py-1.5 rounded-full text-xs font-semibold transition-colors ${
          !active ? "bg-accent text-white" : "bg-surface text-text-secondary border border-border hover:text-text-primary"
        }`}
      >
        All Sectors
      </button>
      {sectors.map((s) => (
        <button
          key={s}
          onClick={() => onSelect(s === active ? null : s)}
          className={`px-3.5 py-1.5 rounded-full text-xs font-semibold transition-colors ${
            s === active ? "bg-accent text-white" : "bg-surface text-text-secondary border border-border hover:text-text-primary"
          }`}
        >
          {s}
        </button>
      ))}
      <div className="flex-1" />
      <select
        value={signalFilter ?? ""}
        onChange={(e) => onSignalChange(e.target.value || null)}
        className="px-3 py-1.5 rounded-md bg-surface border border-border text-xs text-text-secondary"
      >
        <option value="">Signal: All</option>
        {SIGNALS.map((s) => (
          <option key={s} value={s}>{s}</option>
        ))}
      </select>
    </div>
  );
}
