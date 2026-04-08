import { HashRouter, Routes, Route } from "react-router-dom";
import Shell from "./components/layout/Shell";
import { useApi } from "./hooks/useApi";
import { api } from "./lib/api";
import type { ScanResult } from "./lib/types";
import { createContext, useContext, useEffect } from "react";
import Scanner from "./pages/Scanner";
import Home from "./pages/Home";
import Portfolio from "./pages/Portfolio";
import Backtest from "./pages/Backtest";
import Alerts from "./pages/Alerts";
import Accuracy from "./pages/Accuracy";
import Momentum from "./pages/Momentum";
import Watchlist from "./pages/Watchlist";
import { ToastProvider } from "./components/common/Toast";

export const ScanContext = createContext<{
  scan: ScanResult | null;
  loading: boolean;
  refetch: () => void;
}>({ scan: null, loading: true, refetch: () => {} });

export function useScan() {
  return useContext(ScanContext);
}

export default function App() {
  const { data: scan, loading, refetch } = useApi<ScanResult>(() => api.scanCached());

  useEffect(() => {
    const onFocus = () => { refetch(); };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [refetch]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        // global escape fallback — individual modals handle their own close
        document.dispatchEvent(new CustomEvent("global-escape"));
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  return (
    <ToastProvider>
      <ScanContext.Provider value={{ scan, loading, refetch }}>
        <HashRouter>
          <Routes>
            <Route element={<Shell scan={scan} onScanComplete={refetch} />}>
              <Route path="/" element={<Home />} />
              <Route path="/scanner" element={<Scanner />} />
              <Route path="/portfolio" element={<Portfolio />} />
              <Route path="/backtest" element={<Backtest />} />
              <Route path="/alerts" element={<Alerts />} />
              <Route path="/accuracy" element={<Accuracy />} />
              <Route path="/momentum" element={<Momentum />} />
              <Route path="/watchlist" element={<Watchlist />} />
            </Route>
          </Routes>
        </HashRouter>
      </ScanContext.Provider>
    </ToastProvider>
  );
}
