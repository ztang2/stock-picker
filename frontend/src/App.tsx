import { BrowserRouter, Routes, Route } from "react-router-dom";

function Placeholder({ name }: { name: string }) {
  return (
    <div className="flex items-center justify-center h-screen text-text-secondary">
      {name} — coming soon
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Placeholder name="Home" />} />
        <Route path="/scanner" element={<Placeholder name="Scanner" />} />
        <Route path="/portfolio" element={<Placeholder name="Portfolio" />} />
        <Route path="/backtest" element={<Placeholder name="Backtest" />} />
        <Route path="/alerts" element={<Placeholder name="Alerts" />} />
        <Route path="/accuracy" element={<Placeholder name="Accuracy" />} />
        <Route path="/momentum" element={<Placeholder name="Momentum" />} />
      </Routes>
    </BrowserRouter>
  );
}
