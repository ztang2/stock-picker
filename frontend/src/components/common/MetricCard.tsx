interface MetricCardProps {
  label: string;
  value: string;
  subtitle?: string;
  valueColor?: string;
}

export default function MetricCard({ label, value, subtitle, valueColor = "text-text-primary" }: MetricCardProps) {
  return (
    <div className="p-3 rounded-lg bg-surface border border-border">
      <div className="text-[10px] text-text-muted uppercase tracking-wider">{label}</div>
      <div className={`text-xl font-bold mt-0.5 ${valueColor}`}>{value}</div>
      {subtitle && <div className="text-[11px] text-text-secondary mt-0.5">{subtitle}</div>}
    </div>
  );
}
