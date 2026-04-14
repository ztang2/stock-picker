import { NavLink } from "react-router-dom";
import { useState } from "react";
import { Home, BarChart2, Briefcase, TrendingUp, Bell, Target, Zap, Star, ChevronLeft, ChevronRight } from "lucide-react";

const NAV_ITEMS = [
  { to: "/", icon: <Home size={16} />, label: "Home" },
  { to: "/scanner", icon: <BarChart2 size={16} />, label: "Scanner" },
  { to: "/portfolio", icon: <Briefcase size={16} />, label: "Portfolio" },
  { to: "/backtest", icon: <TrendingUp size={16} />, label: "Backtest" },
  { to: "/alerts", icon: <Bell size={16} />, label: "Alerts" },
  { to: "/accuracy", icon: <Target size={16} />, label: "Accuracy" },
  { to: "/momentum", icon: <Zap size={16} />, label: "Momentum" },
  { to: "/watchlist", icon: <Star size={16} />, label: "Watchlist" },
];

export default function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <nav
      className={`flex flex-col bg-surface border-r border-border h-screen sticky top-0 transition-all duration-200 ${
        collapsed ? "w-16" : "w-48"
      }`}
    >
      <div className="flex items-center justify-between p-4 border-b border-border"
        style={{ background: "linear-gradient(180deg, var(--color-accent-dim) 0%, transparent 100%)" }}
      >
        {!collapsed && (
          <span className="text-sm font-bold text-text-primary tracking-wide">Stock Picker</span>
        )}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="text-text-muted hover:text-accent transition-colors text-xs"
        >
          {collapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
        </button>
      </div>
      <div className="flex flex-col gap-0.5 p-2 flex-1">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-all duration-150 ${
                isActive
                  ? "nav-active-glow text-accent font-semibold"
                  : "text-text-secondary hover:bg-accent/[0.05] hover:text-text-primary"
              }`
            }
          >
            <span className="text-base">{item.icon}</span>
            {!collapsed && <span>{item.label}</span>}
          </NavLink>
        ))}
      </div>
    </nav>
  );
}
