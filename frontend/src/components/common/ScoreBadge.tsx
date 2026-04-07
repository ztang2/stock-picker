import { signalColor } from "../../lib/colors";

interface ScoreBadgeProps {
  signal: string;
  className?: string;
}

function badgeGlow(signal: string): string {
  switch (signal) {
    case "STRONG_BUY":
    case "BUY": return "badge-glow-positive";
    case "SELL":
    case "STRONG_SELL": return "badge-glow-danger";
    case "WAIT": return "badge-glow-caution";
    default: return "";
  }
}

export default function ScoreBadge({ signal, className = "" }: ScoreBadgeProps) {
  return (
    <span className={`px-2.5 py-1 rounded-md text-[11px] font-bold ${signalColor(signal)} ${badgeGlow(signal)} ${className}`}>
      {signal}
    </span>
  );
}
