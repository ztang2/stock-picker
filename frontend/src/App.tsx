import { BrowserRouter, Routes, Route } from "react-router-dom";
import Shell from "./components/layout/Shell";
import { useApi } from "./hooks/useApi";
import { api } from "./lib/api";
import type { ScanResult } from "./lib/types";
import { createContext, useContext } from "react";
import Scanner from "./pages/Scanner";
import Home from "./pages/Home";
import Portfolio from "./pages/Portfolio";
import Backtest from "./pages/Backtest";
import Alerts from "./pages/Alerts";
import Accuracy from "./pages/Accuracy";
import Momentum from "./pages/Momentum";

export const ScanContext = createContext<{
  scan: ScanResult | null;
  loading: boolean;
  refetch: () => void;
}>({ scan: null, loading: true, refetch: () => {} });

export function useScan() {
  return useContext(ScanContext);
}

function Placeholder({ name }: { name: string }) {
  return (
    <div className="flex items-center justify-center h-64 text-text-secondary">
      {name} — coming soon
    </div>
  );
}

export default function App() {
  const { data: scan, loading, refetch } = useApi<ScanResult>(() => api.scanCached());

  return (
    <ScanContext.Provider value={{ scan, loading, refetch }}>
      <BrowserRouter>
        <Routes>
          <Route element={<Shell scan={scan} />}>
            <Route path="/" element={<Home />} />
            <Route path="/scanner" element={<Scanner />} />
            <Route path="/portfolio" element={<Portfolio />} />
            <Route path="/backtest" element={<Backtest />} />
            <Route path="/alerts" element={<Alerts />} />
            <Route path="/accuracy" element={<Accuracy />} />
            <Route path="/momentum" element={<Momentum />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ScanContext.Provider>
  );
}
