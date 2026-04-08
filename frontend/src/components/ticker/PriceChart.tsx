import { useEffect, useState } from "react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  ReferenceLine,
  Tooltip,
} from "recharts";
import { api } from "../../lib/api";
import type { ChartData } from "../../lib/types";

interface PriceChartProps {
  ticker: string;
}

export default function PriceChart({ ticker }: PriceChartProps) {
  const [data, setData] = useState<ChartData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api
      .chart(ticker)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [ticker]);

  if (loading) return <div className="h-48 flex items-center justify-center text-text-muted text-sm">Loading chart...</div>;
  if (!data || data.ohlc.length === 0) return null;

  const closes = data.ohlc.map((d) => d.close);
  const minPrice = Math.min(...closes) * 0.98;
  const maxPrice = Math.max(...closes) * 1.02;
  const lastPrice = closes[closes.length - 1];
  const firstPrice = closes[0];
  const isUp = lastPrice >= firstPrice;

  return (
    <div className="rounded-xl bg-surface border border-border p-4">
      <div className="flex justify-between items-center mb-2">
        <span className="text-xs font-semibold text-text-muted uppercase tracking-wider">3-Month Price</span>
        <span className={`text-xs font-data font-semibold ${isUp ? "text-positive" : "text-danger"}`}>
          {isUp ? "+" : ""}{((lastPrice - firstPrice) / firstPrice * 100).toFixed(1)}%
        </span>
      </div>
      <ResponsiveContainer width="100%" height={180}>
        <AreaChart data={data.ohlc} margin={{ top: 5, right: 5, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id={`gradient-${ticker}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={isUp ? "#22c55e" : "#ef4444"} stopOpacity={0.2} />
              <stop offset="100%" stopColor={isUp ? "#22c55e" : "#ef4444"} stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="date"
            tick={{ fontSize: 10, fill: "var(--color-text-muted)" }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(v: string) => v.slice(5)}
            interval={Math.floor(data.ohlc.length / 5)}
          />
          <YAxis
            domain={[minPrice, maxPrice]}
            tick={{ fontSize: 10, fill: "var(--color-text-muted)" }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(v: number) => `$${v.toFixed(0)}`}
            width={45}
          />
          <Tooltip
            contentStyle={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: "6px", fontSize: "12px", color: "var(--color-text-primary)" }}
            labelStyle={{ color: "var(--color-text-muted)" }}
            formatter={(v) => [`$${Number(v).toFixed(2)}`, "Close"]}
          />
          {data.support && (
            <ReferenceLine y={data.support} stroke="#22c55e" strokeDasharray="4 4" strokeOpacity={0.6} />
          )}
          {data.resistance && (
            <ReferenceLine y={data.resistance} stroke="#ef4444" strokeDasharray="4 4" strokeOpacity={0.6} />
          )}
          {data.ma50 && (
            <ReferenceLine y={data.ma50} stroke="#52525b" strokeDasharray="2 2" strokeOpacity={0.4} />
          )}
          <Area
            type="monotone"
            dataKey="close"
            stroke={isUp ? "#22c55e" : "#ef4444"}
            strokeWidth={1.5}
            fill={`url(#gradient-${ticker})`}
          />
        </AreaChart>
      </ResponsiveContainer>
      <div className="flex gap-4 mt-1 text-[10px] text-text-muted">
        {data.support && <span><span className="inline-block w-3 h-px bg-positive mr-1 align-middle" style={{ borderTop: "1px dashed #22c55e" }} />Support ${data.support.toFixed(2)}</span>}
        {data.resistance && <span><span className="inline-block w-3 h-px bg-danger mr-1 align-middle" style={{ borderTop: "1px dashed #ef4444" }} />Resistance ${data.resistance.toFixed(2)}</span>}
        {data.ma50 && <span><span className="inline-block w-3 h-px mr-1 align-middle" style={{ borderTop: "1px dashed #52525b" }} />MA50 ${data.ma50.toFixed(2)}</span>}
      </div>
    </div>
  );
}
