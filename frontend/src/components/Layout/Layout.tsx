import { useState } from "react";
import { Link, useLocation, Outlet } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";

export default function Layout() {
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const { user, isAuthenticated, logout, openAuthModal } = useAuth();

  const navItems = [
    { path: "/", label: "Practice Arena", icon: "grid_view" },
    { path: "/record", label: "Live JAM Session", icon: "sensors", pulse: true },
    { path: "/technical", label: "Technical Drill", icon: "terminal" },
    { path: "/guesstimate", label: "Guesstimate Sizing", icon: "query_stats" },
    { path: "/hr", label: "HR Behavioral", icon: "diversity_3" },
    { path: "/dashboard", label: "Pattern & Progress", icon: "insights" },
  ];

  return (
    <div className="min-h-screen bg-surface text-on-surface flex">
      {/* Mobile Menu Backdrop */}
      {mobileOpen && (
        <div
          className="fixed inset-0 bg-black/60 z-40 md:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* VerbalIQ Left Fixed Sidebar */}
      <aside
        className={`fixed left-0 top-0 h-full w-72 bg-surface-container-low border-r border-outline-variant/30 z-50 flex flex-col justify-between py-6 px-4 shadow-[0_1px_8px_rgba(0,0,0,0.4)] transition-transform duration-200 ${
          mobileOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"
        }`}
      >
        <div className="flex flex-col gap-6">
          {/* Logo & Version */}
          <Link
            to="/"
            onClick={() => setMobileOpen(false)}
            className="flex items-center gap-3 px-3 hover:opacity-90 transition-opacity"
          >
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-primary-container via-primary to-secondary flex items-center justify-center text-on-primary-container font-bold text-lg shadow-md shadow-primary/20">
              <span className="material-symbols-outlined text-[22px] text-white">mic</span>
            </div>
            <div className="flex flex-col">
              <span className="font-headline-sm text-[18px] text-on-surface tracking-tight font-bold">
                Verbal<span className="text-primary">IQ</span>
              </span>
              <span className="font-label-caps text-[10px] text-secondary uppercase tracking-widest font-semibold">
                AI Coach v2.4
              </span>
            </div>
          </Link>

          <div className="h-px w-full bg-outline-variant/30" />

          {/* Workspaces Label */}
          <div className="px-3">
            <span className="font-label-caps text-[11px] uppercase text-outline tracking-wider font-semibold">
              Workspaces
            </span>
          </div>

          {/* Navigation Links */}
          <nav className="flex flex-col gap-1.5">
            {navItems.map((item) => {
              const isActive =
                item.path === "/"
                  ? location.pathname === "/"
                  : location.pathname.startsWith(item.path);

              return (
                <Link
                  key={item.path}
                  to={item.path}
                  onClick={() => setMobileOpen(false)}
                  className={`flex items-center gap-3 px-3.5 py-2.5 rounded-lg transition-colors font-medium text-sm ${
                    isActive
                      ? "bg-primary-container text-on-primary-container font-semibold shadow-sm"
                      : "text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface"
                  }`}
                >
                  <span className="material-symbols-outlined text-[20px]">
                    {item.icon}
                  </span>
                  <span className="flex-1">{item.label}</span>
                  {item.pulse && (
                    <span className="w-2 h-2 rounded-full bg-tertiary animate-pulse" />
                  )}
                </Link>
              );
            })}
          </nav>
        </div>

        {/* Telemetry Widgets */}
        <div className="flex flex-col gap-4 px-3">
          <div className="bg-surface-container rounded-lg p-3.5 border border-outline-variant/30">
            <div className="flex items-center justify-between mb-2">
              <span className="font-label-caps text-[10px] uppercase text-outline font-bold">
                Cognitive Load
              </span>
              <span className="font-label-numeric-sm text-[11px] text-tertiary font-semibold">
                Optimal 42%
              </span>
            </div>
            <div className="w-full bg-surface-container-highest h-1.5 rounded-full overflow-hidden">
              <div
                className="bg-tertiary h-full rounded-full transition-all duration-500"
                style={{ width: "42%" }}
              />
            </div>
          </div>

          <div className="flex items-center justify-between text-on-surface-variant text-xs pt-2 border-t border-outline-variant/30">
            <span>Engine Status</span>
            <span className="flex items-center gap-1.5 font-label-numeric-sm text-[11px] text-secondary font-medium">
              <span className="w-1.5 h-1.5 rounded-full bg-secondary" />
              Online
            </span>
          </div>
        </div>
      </aside>

      {/* Main View Area */}
      <div className="flex-1 flex flex-col md:pl-72 min-w-0">
        {/* Top Header */}
        <header className="fixed top-0 left-0 md:left-72 right-0 h-16 bg-surface/85 backdrop-blur-xl border-b border-outline-variant/30 z-40 flex items-center justify-between px-4 sm:px-6 shadow-[0_1px_8px_rgba(0,0,0,0.3)]">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setMobileOpen(!mobileOpen)}
              className="p-1.5 rounded-lg bg-surface-container text-on-surface md:hidden"
            >
              <span className="material-symbols-outlined text-[20px]">menu</span>
            </button>

            <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-lg bg-surface-container border border-outline-variant/40">
              <span className="material-symbols-outlined text-[18px] text-secondary">
                tune
              </span>
              <span className="font-label-caps text-[11px] uppercase text-on-surface tracking-wider font-semibold">
                Mode:
              </span>
              <span className="text-xs text-secondary font-medium">
                Adaptive JAM & Technical
              </span>
            </div>

            <span className="font-label-numeric-sm text-[11px] px-2.5 py-0.5 rounded-full bg-surface-container-high text-primary border border-primary/20">
              {isAuthenticated ? "Tier 3 Candidate" : "Guest Sandbox"}
            </span>
          </div>

          <div className="flex items-center gap-3 sm:gap-4">
            <Link
              to="/record"
              className="flex items-center gap-2 px-3 sm:px-4 py-1.5 rounded-lg bg-primary text-on-primary font-headline-sm text-xs sm:text-[13px] font-semibold hover:bg-primary-fixed-dim transition-colors shadow-[0_0_15px_rgba(192,193,255,0.25)]"
            >
              <span className="material-symbols-outlined text-[18px]">play_arrow</span>
              <span>Quick Launch</span>
            </Link>

            <div className="hidden sm:flex items-center gap-2 px-3 py-1 rounded-lg bg-surface-container-high border border-outline-variant/40">
              <span className="text-sm">🔥</span>
              <span className="font-label-numeric-sm text-xs text-on-surface font-medium">
                14 Days Streak
              </span>
            </div>

            <div className="h-5 w-px bg-outline-variant/30 hidden sm:block" />

            {isAuthenticated && user ? (
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-full bg-gradient-to-br from-primary/30 to-secondary/30 ring-1 ring-primary/40 flex items-center justify-center font-bold text-xs text-primary shadow-sm">
                  {(user.full_name || user.username || "U").substring(0, 2).toUpperCase()}
                </div>
                <div className="hidden xl:flex flex-col text-left">
                  <span className="text-xs font-semibold text-on-surface leading-none">
                    {user.full_name || user.username}
                  </span>
                  <span className="font-label-numeric-sm text-[10px] text-outline leading-tight mt-0.5 truncate max-w-[120px]">
                    {user.email}
                  </span>
                </div>
                <button
                  type="button"
                  onClick={logout}
                  title="Sign Out"
                  className="p-1.5 rounded-lg bg-surface-container hover:bg-surface-container-high text-outline hover:text-on-surface transition-colors cursor-pointer ml-1"
                >
                  <span className="material-symbols-outlined text-[18px]">logout</span>
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={openAuthModal}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-surface-container-high border border-outline-variant/50 hover:border-primary/50 text-on-surface hover:text-primary transition-all text-xs font-semibold cursor-pointer shadow-sm"
              >
                <span className="material-symbols-outlined text-[16px] text-primary">login</span>
                <span>Sign In</span>
              </button>
            )}
          </div>
        </header>

        {/* Content Outlet */}
        <main className="relative pt-16 w-full min-h-screen bg-surface">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

