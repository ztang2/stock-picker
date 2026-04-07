import { useApi } from "../../hooks/useApi";

interface Peer {
  ticker: string;
  name: string;
  industry?: string;
  market_cap?: number;
  pe_ratio?: number;
  ps_ratio?: number;
  ev_ebitda?: number;
  revenue_growth?: number;
  profit_margin?: number;
}

interface CompsData {
  ticker: string;
  target?: Peer;
  peers?: Peer[];
  comps_score?: number;
  verdict?: string;
}

const VERDICT_COLOR: Record<string, string> = {
  UNDERVALUED: "text-positive",
  SLIGHTLY_UNDERVALUED: "text-positive",
  FAIRLY_VALUED: "text-caution",
  SLIGHTLY_OVERVALUED: "text-caution",
  OVERVALUED: "text-danger",
};

function fmt(val: number | null | undefined, decimals = 1): string {
  if (val == null) return "—";
  return val.toFixed(decimals);
}

function fmtPct(val: number | null | undefined): string {
  if (val == null) return "—";
  return `${(val * 100).toFixed(1)}%`;
}

function fmtCap(val: number | null | undefined): string {
  if (val == null) return "—";
  if (val >= 1e12) return `$${(val / 1e12).toFixed(1)}T`;
  if (val >= 1e9) return `$${(val / 1e9).toFixed(1)}B`;
  return `$${(val / 1e6).toFixed(0)}M`;
}

export default function CompsTab({ ticker }: { ticker: string }) {
  const { data, loading, error } = useApi<CompsData>(
    () => fetch(`/comps/${ticker}`).then(r => r.json()),
    [ticker]
  );
  if (loading) return <div className="p-4 text-text-secondary text-sm">Loading comps...</div>;
  if (error || !data) return <div className="p-4 text-text-secondary text-sm">Comps data unavailable</div>;

  const allRows = [
    ...(data.target ? [{ ...data.target, isTarget: true }] : []),
    ...(data.peers ?? []).map(p => ({ ...p, isTarget: false })),
  ];

  return (
    <div className="p-4">
      <div className="flex items-center gap-3 mb-4">
        <span className={`text-lg font-bold ${VERDICT_COLOR[data.verdict ?? ""] ?? "text-text-primary"}`}>
          {data.verdict?.replace(/_/g, " ") ?? "—"}
        </span>
        <span className="text-sm text-text-secondary">
          Comps Score: {data.comps_score ?? "—"} · {(data.peers ?? []).length} peers
        </span>
      </div>
      <div className="rounded-lg border border-border overflow-hidden">
        <table className="w-full text-xs">
          <thead className="bg-base">
            <tr>
              <th className="py-2 px-3 text-left text-text-muted uppercase">Ticker</th>
              <th className="py-2 px-3 text-left text-text-muted uppercase">Mkt Cap</th>
              <th className="py-2 px-3 text-right text-text-muted uppercase">P/E</th>
              <th className="py-2 px-3 text-right text-text-muted uppercase">P/S</th>
              <th className="py-2 px-3 text-right text-text-muted uppercase">EV/EBITDA</th>
              <th className="py-2 px-3 text-right text-text-muted uppercase">Rev Growth</th>
              <th className="py-2 px-3 text-right text-text-muted uppercase">Margin</th>
            </tr>
          </thead>
          <tbody>
            {allRows.map((row) => (
              <tr
                key={row.ticker}
                className={`border-t border-border ${row.isTarget ? "bg-accent/5 font-semibold" : ""}`}
              >
                <td className="py-2 px-3 text-text-primary">
                  {row.ticker} {row.isTarget && <span className="text-accent text-[10px]">TARGET</span>}
                </td>
                <td className="py-2 px-3 text-text-secondary">{fmtCap(row.market_cap)}</td>
                <td className="py-2 px-3 text-right text-text-primary">{fmt(row.pe_ratio)}</td>
                <td className="py-2 px-3 text-right text-text-primary">{fmt(row.ps_ratio)}</td>
                <td className="py-2 px-3 text-right text-text-primary">{fmt(row.ev_ebitda)}</td>
                <td className="py-2 px-3 text-right text-text-primary">{fmtPct(row.revenue_growth)}</td>
                <td className="py-2 px-3 text-right text-text-primary">{fmtPct(row.profit_margin)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
