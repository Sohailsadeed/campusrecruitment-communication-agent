import { Link, useLocation } from "react-router-dom";
import { Mic } from "lucide-react";

export default function Header() {
  const location = useLocation();
  return (
    <header className="border-b border-white/10 backdrop-blur-md bg-surface-950/60 sticky top-0 z-20">
      <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2 group">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-primary-400 to-primary-700 flex items-center justify-center shadow-lg shadow-primary-900/40 group-hover:scale-105 transition-transform">
            <Mic className="w-5 h-5 text-white" />
          </div>
          <div>
            <div className="text-lg font-bold tracking-tight">SpeakFlow</div>
            <div className="text-[10px] uppercase tracking-wider text-primary-300">
              AI Speaking Coach
            </div>
          </div>
        </Link>

        <div className="text-xs text-slate-400 hidden md:block">
          {location.pathname === "/record"
            ? "Recording Studio"
            : location.pathname.startsWith("/analysis")
            ? "Session Analysis"
            : location.pathname === "/dashboard"
            ? "Your Progress"
            : "Welcome back"}
        </div>
      </div>
    </header>
  );
}
