import { useState } from "react";
import { Navigate, useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function AuthPage() {
  const { isAuthenticated, login, register, loading } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [isRegister, setIsRegister] = useState(false);

  // Form fields
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [username, setUsername] = useState("");
  const [fullName, setFullName] = useState("");

  const [formLoading, setFormLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // If already authenticated, redirect to destination or home
  const from = (location.state as any)?.from?.pathname || "/";
  if (!loading && isAuthenticated) {
    return <Navigate to={from} replace />;
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setFormLoading(true);

    try {
      if (isRegister) {
        if (!email.trim() || !password || !username.trim()) {
          setError("Please fill out all required fields.");
          setFormLoading(false);
          return;
        }
        await register({
          email: email.trim(),
          username: username.trim(),
          full_name: fullName.trim() || undefined,
          password,
        });
      } else {
        if (!email.trim() || !password) {
          setError("Please enter your email/username and password.");
          setFormLoading(false);
          return;
        }
        await login({ email: email.trim(), password });
      }
      navigate(from, { replace: true });
    } catch (err: any) {
      const rawDetail = err?.response?.data?.detail;
      let errorMsg = "Authentication failed. Please check your credentials.";
      if (typeof rawDetail === "string") {
        errorMsg = rawDetail;
      } else if (Array.isArray(rawDetail) && rawDetail.length > 0) {
        errorMsg = rawDetail
          .map((d: any) => d.msg || (typeof d === "string" ? d : JSON.stringify(d)))
          .join(", ");
      } else if (err?.message) {
        errorMsg = err.message;
      }
      setError(errorMsg);
    } finally {
      setFormLoading(false);
    }
  };

  return (
    <div className="relative min-h-screen w-full flex items-center justify-center p-4 bg-background overflow-hidden selection:bg-secondary/30 selection:text-on-surface">
      {/* Ambient Backdrop Aura */}
      <div className="pointer-events-none absolute -top-40 right-1/4 w-[700px] h-[400px] bg-primary/10 rounded-full blur-[140px]" />
      <div className="pointer-events-none absolute top-1/2 -left-20 w-[500px] h-[350px] bg-secondary-container/10 rounded-full blur-[120px]" />

      <div className="relative z-10 w-full max-w-md rounded-2xl bg-surface-container-low border border-outline-variant/30 shadow-2xl overflow-hidden p-6 sm:p-8 flex flex-col gap-6">
        {/* Brand Header */}
        <div className="flex flex-col items-center text-center gap-2">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-primary to-secondary flex items-center justify-center shadow-lg shadow-primary/20">
            <span className="material-symbols-outlined text-[28px] text-on-primary">
              graphic_eq
            </span>
          </div>
          <h1 className="font-display-hero text-2xl sm:text-3xl font-extrabold text-on-surface tracking-tight mt-1">
            VerbalIQ
          </h1>
          <p className="text-xs sm:text-sm text-on-surface-variant max-w-xs leading-relaxed">
            AI-Powered Verbal Communication &amp; Placement Interview Arena
          </p>
        </div>

        {/* Tab Toggle */}
        <div className="grid grid-cols-2 p-1 rounded-xl bg-surface-container-high border border-outline-variant/30">
          <button
            type="button"
            onClick={() => {
              setIsRegister(false);
              setError(null);
            }}
            className={`py-2 text-xs font-bold rounded-lg transition-all ${
              !isRegister
                ? "bg-secondary text-on-secondary shadow-md"
                : "text-on-surface-variant hover:text-on-surface"
            }`}
          >
            Sign In
          </button>
          <button
            type="button"
            onClick={() => {
              setIsRegister(true);
              setError(null);
            }}
            className={`py-2 text-xs font-bold rounded-lg transition-all ${
              isRegister
                ? "bg-secondary text-on-secondary shadow-md"
                : "text-on-surface-variant hover:text-on-surface"
            }`}
          >
            Create Account
          </button>
        </div>

        {/* Alert / Error Box */}
        {error && (
          <div className="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs flex items-center gap-2 leading-relaxed">
            <span className="material-symbols-outlined text-[18px] flex-shrink-0">
              error
            </span>
            <span>{error}</span>
          </div>
        )}

        {/* Form Body */}
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          {isRegister && (
            <>
              <div>
                <label className="block text-xs font-semibold text-on-surface-variant mb-1 font-label-caps uppercase">
                  Full Name
                </label>
                <input
                  type="text"
                  placeholder="Mohammad Sohail"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  className="w-full px-3.5 py-2.5 rounded-lg bg-surface-container border border-outline-variant/30 text-on-surface text-sm focus:outline-none focus:border-secondary transition-colors"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-on-surface-variant mb-1 font-label-caps uppercase">
                  Username *
                </label>
                <input
                  type="text"
                  required
                  placeholder="sohail_dev"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="w-full px-3.5 py-2.5 rounded-lg bg-surface-container border border-outline-variant/30 text-on-surface text-sm focus:outline-none focus:border-secondary transition-colors"
                />
              </div>
            </>
          )}

          <div>
            <label className="block text-xs font-semibold text-on-surface-variant mb-1 font-label-caps uppercase">
              {isRegister ? "Email Address *" : "Email or Username *"}
            </label>
            <input
              type={isRegister ? "email" : "text"}
              required
              placeholder={isRegister ? "candidate@university.edu" : "email or username"}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full px-3.5 py-2.5 rounded-lg bg-surface-container border border-outline-variant/30 text-on-surface text-sm focus:outline-none focus:border-secondary transition-colors"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-on-surface-variant mb-1 font-label-caps uppercase">
              Password *
            </label>
            <input
              type="password"
              required
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-3.5 py-2.5 rounded-lg bg-surface-container border border-outline-variant/30 text-on-surface text-sm focus:outline-none focus:border-secondary transition-colors"
            />
          </div>

          <button
            type="submit"
            disabled={formLoading}
            className="w-full mt-2 py-3 rounded-lg bg-secondary text-on-secondary font-headline-sm text-xs font-bold hover:bg-secondary/90 transition-all shadow-md shadow-secondary/20 flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
          >
            {formLoading ? (
              <span className="w-4 h-4 rounded-full border-2 border-on-secondary border-t-transparent animate-spin" />
            ) : (
              <>
                <span className="material-symbols-outlined text-[18px]">
                  {isRegister ? "person_add" : "login"}
                </span>
                <span>{isRegister ? "Complete Registration" : "Sign In & Enter Arena"}</span>
              </>
            )}
          </button>
        </form>

        <div className="text-center text-xs text-outline font-body-sm">
          Secured with encrypted JWT auth &amp; individual PostgreSQL profile sandboxing.
        </div>
      </div>
    </div>
  );
}
