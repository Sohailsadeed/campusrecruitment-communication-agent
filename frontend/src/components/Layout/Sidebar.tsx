import { NavLink } from "react-router-dom";
import { Home, Mic, LayoutDashboard, Settings } from "lucide-react";

const items = [
  { to: "/", label: "Home", icon: Home },
  { to: "/record", label: "Record", icon: Mic },
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/settings", label: "Settings", icon: Settings },
];

export default function Sidebar() {
  return (
    <aside className="hidden lg:flex flex-col w-56 shrink-0 border-r border-white/10 bg-surface-950/40 p-4 gap-1">
      {items.map(({ to, label, icon: Icon }) => (
        <NavLink
          key={to}
          to={to}
          end={to === "/"}
          className={({ isActive }) =>
            `flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all ${
              isActive
                ? "bg-primary-600/20 text-primary-200 border border-primary-500/30"
                : "text-slate-300 hover:bg-white/5 border border-transparent"
            }`
          }
        >
          <Icon className="w-4 h-4" />
          {label}
        </NavLink>
      ))}
    </aside>
  );
}
