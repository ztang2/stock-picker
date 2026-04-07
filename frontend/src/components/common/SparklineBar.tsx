interface SparklineBarProps {
  values: number[];
  height?: number;
}

export default function SparklineBar({ values, height = 28 }: SparklineBarProps) {
  if (values.length === 0) return null;
  const max = Math.max(...values);
  const isRising = values.length >= 2 && values[values.length - 1] > values[0];
  const isFalling = values.length >= 2 && values[values.length - 1] < values[0] - 3;

  return (
    <div className="flex items-end gap-0.5 px-1" style={{ height }}>
      {values.map((v, i) => {
        const pct = max > 0 ? (v / max) * 100 : 0;
        const isRecent = i >= values.length - 2;
        let color = "bg-accent";
        if (isRecent) color = isRising ? "bg-positive" : isFalling ? "bg-caution" : "bg-accent";
        else if (i < values.length - 3) color = "bg-border";
        return <div key={i} className={`flex-1 rounded-sm ${color}`} style={{ height: `${pct}%` }} />;
      })}
    </div>
  );
}
