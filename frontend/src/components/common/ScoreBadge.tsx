import { signalColor } from "../../lib/colors";

interface ScoreBadgeProps {
  signal: string;
  className?: string;
}

export default function ScoreBadge({ signal, className = "" }: ScoreBadgeProps) {
  return (
    <span className={`px-2.5 py-1 rounded-md text-[11px] font-bold ${signalColor(signal)} ${className}`}>
      {signal}
    </span>
  );
}
