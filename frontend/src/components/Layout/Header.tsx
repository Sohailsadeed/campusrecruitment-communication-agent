import { Link, useLocation } from "react-router-dom";
import { Mic, Sparkles } from "lucide-react";

const NAV_ITEMS = [
  { path: "/", label: "Home" },
  { path: "/record", label: "JAM Studio" },
  { path: "/dashboard", label: "Dashboard" },
  { path: "/settings", label: "Settings" },
];

export default function Header() {
  const location = useLocation();

  return (
    <header className="bg-white border-b border-slate-200/80 px-4 sm:px-6 py-3 flex items-center justify-between sticky top-0 z-20 shadow-xs">
      <div className="flex items-center gap-8">
        <Link to="/" className="flex items-center gap-2.5 group">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-violet-600 to-fuchsia-600 flex items-center justify-center text-white shadow-sm shadow-violet-500/30">
            <Mic className="w-4 h-4" />
          </div>
          <span className="text-lg font-bold text-violet-600 tracking-tight">
            InterviewForge
          </span>
          <span className="hidden sm:inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full bg-violet-50 text-violet-700 border border-violet-200">
            <Sparkles className="w-3 h-3 text-violet-600" />
            JAM Round
          </span>
        </Link>

        <nav className="hidden md:flex items-center gap-1">
          {NAV_ITEMS.map((item) => {
            const isActive =
              item.path === "/"
                ? location.pathname === "/"
                : location.pathname.startsWith(item.path);

            return (
              <Link
                key={item.path}
                to={item.path}
                className={`text-sm px-3.5 py-1.5 rounded-lg transition-colors font-medium ${
                  isActive
                    ? "bg-violet-50 text-violet-700 font-semibold"
                    : "text-slate-600 hover:text-slate-900 hover:bg-slate-100"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      </div>

      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-full bg-violet-100 text-violet-700 flex items-center justify-center text-xs font-semibold">
            C
          </div>
          <span className="text-sm font-medium text-slate-700 hidden sm:inline">
            Candidate
          </span>
        </div>
      </div>
    </header>
  );
}
