import { useApi } from "../../hooks/useApi";
import { api } from "../../lib/api";

export default function CompsTab({ ticker }: { ticker: string }) {
  const { data, loading } = useApi(() => api.comps(ticker), [ticker]);
  if (loading) return <div className="p-4 text-text-secondary text-sm">Loading comps...</div>;
  if (!data) return <div className="p-4 text-text-secondary text-sm">Comps data unavailable</div>;
  return <div className="p-4"><pre className="text-xs text-text-secondary whitespace-pre-wrap">{JSON.stringify(data, null, 2)}</pre></div>;
}
