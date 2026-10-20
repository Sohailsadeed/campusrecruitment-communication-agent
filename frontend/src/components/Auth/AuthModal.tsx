import { useState } from "react";
import { useAuth } from "../../context/AuthContext";

export default function AuthModal() {
  const { isAuthModalOpen, closeAuthModal, login, register } = useAuth();
  const [isRegister, setIsRegister] = useState(false);

  // Form fields
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [username, setUsername] = useState("");
  const [fullName, setFullName] = useState("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isAuthModalOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      if (isRegister) {
        if (!email.trim() || !password || !username.trim()) {
          setError("Please fill out all required fields.");
          setLoading(false);
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
          setError("Please enter your email and password.");
          setLoading(false);
          return;
        }
        await login({ email: email.trim(), password });
      }
    } catch (err: any) {
      const detail =
        err?.response?.data?.detail ||
        err?.message ||
        "Authentication failed. Please verify credentials.";
      setError(String(detail));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/75 backdrop-blur-md z-50 flex items-center justify-center p-4">
      {/* Click outside to close */}
      <div className="fixed inset-0 -z-10" onClick={closeAuthModal} />

      <div className="relative w-full max-w-md bg-surface-container-low border border-outline-variant/40 rounded-2xl p-6 sm:p-8 shadow-2xl overflow-hidden flex flex-col gap-6">
        {/* Ambient Top Glow */}
        <div className="pointer-events-none absolute -top-20 -right-20 w-52 h-52 bg-primary/20 rounded-full blur-3xl" />
        <div className="pointer-events-none absolute -bottom-20 -left-20 w-52 h-52 bg-secondary/15 rounded-full blur-3xl" />

        {/* Modal Header */}
        <div className="relative z-10 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary via-primary-container to-secondary flex items-center justify-center shadow-md">
              <span className="material-symbols-outlined text-[22px] text-white">person</span>
            </div>
            <div className="flex flex-col">
              <span className="font-headline-sm text-lg font-bold text-on-surface">
                {isRegister ? "Join VerbalIQ" : "Welcome Back"}
              </span>
              <span className="font-label-caps text-[10px] text-outline uppercase tracking-wider font-semibold">
                Universal Candidate Account
              </span>
            </div>
          </div>

          <button
            type="button"
            onClick={closeAuthModal}
            className="w-8 h-8 rounded-lg bg-surface-container hover:bg-surface-container-high flex items-center justify-center text-outline hover:text-on-surface transition-colors cursor-pointer"
          >
            <span className="material-symbols-outlined text-[18px]">close</span>
          </button>
        </div>

        {/* Mode Toggle Pills */}
        <div className="relative z-10 flex rounded-xl bg-surface-container p-1 border border-outline-variant/30">
          <button
            type="button"
            onClick={() => {
              setIsRegister(false);
              setError(null);
            }}
            className={`flex-1 py-2 text-xs font-semibold rounded-lg transition-all ${
              !isRegister
                ? "bg-surface-container-high text-on-surface shadow-sm font-bold"
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
            className={`flex-1 py-2 text-xs font-semibold rounded-lg transition-all ${
              isRegister
                ? "bg-surface-container-high text-on-surface shadow-sm font-bold"
                : "text-on-surface-variant hover:text-on-surface"
            }`}
          >
            Create Account
          </button>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="relative z-10 p-3.5 rounded-xl bg-error-container/20 border border-error/30 text-error text-xs flex items-center gap-2">
            <span className="material-symbols-outlined text-[18px] flex-shrink-0">error</span>
            <span>{error}</span>
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} className="relative z-10 flex flex-col gap-4">
          {isRegister && (
            <>
              <div>
                <label className="text-xs text-outline font-label-caps uppercase block mb-1.5 font-semibold">
                  Full Name (Optional)
                </label>
                <input
                  type="text"
                  placeholder="e.g. Alex Rivera"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  className="w-full px-3.5 py-2.5 rounded-lg bg-surface-container border border-outline-variant/40 text-on-surface text-xs focus:outline-none focus:border-secondary transition-colors"
                />
              </div>

              <div>
                <label className="text-xs text-outline font-label-caps uppercase block mb-1.5 font-semibold">
                  Username *
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. alexrivera"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="w-full px-3.5 py-2.5 rounded-lg bg-surface-container border border-outline-variant/40 text-on-surface text-xs focus:outline-none focus:border-secondary transition-colors"
                />
              </div>
            </>
          )}

          <div>
            <label className="text-xs text-outline font-label-caps uppercase block mb-1.5 font-semibold">
              Email Address *
            </label>
            <input
              type="email"
              required
              placeholder="candidate@verbal.iq"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full px-3.5 py-2.5 rounded-lg bg-surface-container border border-outline-variant/40 text-on-surface text-xs focus:outline-none focus:border-secondary transition-colors"
            />
          </div>

          <div>
            <label className="text-xs text-outline font-label-caps uppercase block mb-1.5 font-semibold">
              Password *
            </label>
            <input
              type="password"
              required
              minLength={6}
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-3.5 py-2.5 rounded-lg bg-surface-container border border-outline-variant/40 text-on-surface text-xs focus:outline-none focus:border-secondary transition-colors"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full mt-2 py-3 px-4 rounded-xl bg-gradient-to-r from-primary via-primary-container to-secondary text-white font-headline-sm text-xs font-bold hover:opacity-95 transition-all shadow-lg shadow-primary/25 cursor-pointer disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {loading ? (
              <>
                <span className="material-symbols-outlined animate-spin text-[18px]">refresh</span>
                <span>Authenticating...</span>
              </>
            ) : (
              <>
                <span>{isRegister ? "Create Free Account" : "Sign In to Studio"}</span>
                <span className="material-symbols-outlined text-[18px]">arrow_forward</span>
              </>
            )}
          </button>
        </form>

        <p className="relative z-10 text-[11px] text-center text-outline leading-tight">
          Your interviews, RAG indexed resumes, and speech telemetry will be privately tied to your account.
        </p>
      </div>
    </div>
  );
}
