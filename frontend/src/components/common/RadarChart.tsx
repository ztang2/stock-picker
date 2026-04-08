import { scoreHex } from "../../lib/colors";

interface RadarChartProps {
  scores: { fund: number; val: number; tech: number; risk: number; grow: number };
  size?: number;
  showLabels?: boolean;
}

const AXES = [
  { key: "fund" as const, label: "Fund", angle: -90 },
  { key: "val" as const, label: "Val", angle: -18 },
  { key: "tech" as const, label: "Tech", angle: 54 },
  { key: "risk" as const, label: "Risk", angle: 126 },
  { key: "grow" as const, label: "Grow", angle: 198 },
];

function polarToXY(angle: number, radius: number, cx: number, cy: number) {
  const rad = (angle * Math.PI) / 180;
  return { x: cx + radius * Math.cos(rad), y: cy + radius * Math.sin(rad) };
}

function makePolygon(scores: Record<string, number>, maxR: number, cx: number, cy: number) {
  return AXES.map(({ key, angle }) => {
    const r = (scores[key] / 100) * maxR;
    const { x, y } = polarToXY(angle, r, cx, cy);
    return `${x},${y}`;
  }).join(" ");
}

function makeGridPolygon(pct: number, maxR: number, cx: number, cy: number) {
  return AXES.map(({ angle }) => {
    const { x, y } = polarToXY(angle, maxR * pct, cx, cy);
    return `${x},${y}`;
  }).join(" ");
}

export default function RadarChart({ scores, size = 72, showLabels = true }: RadarChartProps) {
  const vb = 100;
  const cx = vb / 2;
  const cy = vb / 2;
  const maxR = 35;
  const labelR = maxR + (showLabels ? 12 : 0);

  const avgScore = (scores.fund + scores.val + scores.tech + scores.risk + scores.grow) / 5;
  const fillColor = scoreHex(avgScore);

  return (
    <svg viewBox={`0 0 ${vb} ${vb}`} width={size} height={size}>
      {[1, 0.66, 0.33].map((pct) => (
        <polygon
          key={pct}
          points={makeGridPolygon(pct, maxR, cx, cy)}
          fill="none"
          stroke="#27272a"
          strokeWidth="0.5"
          opacity={0.4 * pct}
        />
      ))}
      {AXES.map(({ key, angle }) => {
        const { x, y } = polarToXY(angle, maxR, cx, cy);
        return <line key={key} x1={cx} y1={cy} x2={x} y2={y} stroke="#27272a" strokeWidth="0.5" opacity="0.3" />;
      })}
      <polygon points={makePolygon(scores, maxR, cx, cy)} fill={`${fillColor}20`} stroke={fillColor} strokeWidth="1.5" />
      {AXES.map(({ key, angle }) => {
        const r = (scores[key] / 100) * maxR;
        const { x, y } = polarToXY(angle, r, cx, cy);
        return <circle key={key} cx={x} cy={y} r={showLabels ? 2.5 : 1.5} fill={scoreHex(scores[key])} />;
      })}
      {showLabels &&
        AXES.map(({ key, label, angle }) => {
          const { x, y } = polarToXY(angle, labelR, cx, cy);
          const anchor = x < cx - 5 ? "end" : x > cx + 5 ? "start" : "middle";
          return (
            <text key={key} x={x} y={y} textAnchor={anchor} dominantBaseline="middle" fill="#52525b" fontSize="6" fontWeight="600">
              {showLabels ? `${label} ${scores[key]}` : label}
            </text>
          );
        })}
    </svg>
  );
}
