export function scoreColor(score: number): string {
  if (score > 75) return "text-positive";
  if (score >= 50) return "text-caution";
  return "text-danger";
}

export function scoreBg(score: number): string {
  if (score > 75) return "bg-positive/15 text-positive";
  if (score >= 50) return "bg-caution/15 text-caution";
  return "bg-danger/15 text-danger";
}

export function scoreHex(score: number): string {
  if (score > 75) return "#22c55e";
  if (score >= 50) return "#d4a853";
  return "#ef4444";
}

export function signalColor(signal: string): string {
  switch (signal) {
    case "STRONG_BUY": return "bg-positive/15 text-positive";
    case "BUY": return "bg-positive/10 text-positive";
    case "HOLD": return "bg-text-secondary/15 text-text-secondary";
    case "WAIT": return "bg-caution/15 text-caution";
    case "SELL":
    case "STRONG_SELL": return "bg-danger/15 text-danger";
    default: return "bg-text-secondary/15 text-text-secondary";
  }
}

export function pnlColor(value: number): string {
  if (value > 0) return "text-positive";
  if (value < 0) return "text-danger";
  return "text-text-secondary";
}
