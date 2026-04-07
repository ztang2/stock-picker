import { NavLink } from "react-router-dom";
import { useState } from "react";

const NAV_ITEMS = [
  { to: "/", icon: "🏠", label: "Home" },
  { to: "/scanner", icon: "📊", label: "Scanner" },
  { to: "/portfolio", icon: "💼", label: "Portfolio" },
  { to: "/backtest", icon: "📈", label: "Backtest" },
  { to: "/alerts", icon: "🔔", label: "Alerts" },
  { to: "/accuracy", icon: "🎯", label: "Accuracy" },
  { to: "/momentum", icon: "🚀", label: "Momentum" },
];

export default function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <nav
      className={`flex flex-col bg-surface border-r border-border h-screen sticky top-0 transition-all duration-200 ${
        collapsed ? "w-16" : "w-48"
      }`}
    >
      <div className="flex items-center justify-between p-4 border-b border-border">
        {!collapsed && <span className="text-sm font-bold text-text-primary">Stock Picker</span>}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="text-text-muted hover:text-text-primary text-xs"
        >
          {collapsed ? "→" : "←"}
        </button>
      </div>
      <div className="flex flex-col gap-1 p-2 flex-1">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                isActive
                  ? "bg-accent/15 text-accent font-semibold"
                  : "text-text-secondary hover:bg-surface hover:text-text-primary"
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
