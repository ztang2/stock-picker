import { useApi } from "../../hooks/useApi";
import { api } from "../../lib/api";

export default function DCFTab({ ticker }: { ticker: string }) {
  const { data, loading } = useApi(() => api.dcf(ticker), [ticker]);
  if (loading) return <div className="p-4 text-text-secondary text-sm">Loading DCF...</div>;
  if (!data) return <div className="p-4 text-text-secondary text-sm">DCF data unavailable</div>;
  return <div className="p-4"><pre className="text-xs text-text-secondary whitespace-pre-wrap">{JSON.stringify(data, null, 2)}</pre></div>;
}
