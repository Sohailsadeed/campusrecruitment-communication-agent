import { useState } from "react";
import Card from "../components/Common/Card";
import Button from "../components/Common/Button";

export default function SettingsPage() {
  const [apiUrl, setApiUrl] = useState(
    (import.meta.env.VITE_API_URL as string | undefined) ||
      "http://localhost:8000"
  );
  const [model, setModel] = useState(
    () => localStorage.getItem("speakflow_model") || "qwen3.5:4b"
  );
  const [saved, setSaved] = useState(false);

  function handleSave() {
    localStorage.setItem("speakflow_api_url", apiUrl);
    localStorage.setItem("speakflow_model", model);
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  }

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold text-slate-900 tracking-tight">Settings</h1>
        <p className="text-slate-500 text-sm mt-1">Configure your speech evaluator environment and model endpoints.</p>
      </div>

      <Card className="space-y-5">
        <div className="space-y-1.5">
          <label className="block text-xs uppercase tracking-wide font-semibold text-slate-500">
            Backend API URL
          </label>
          <input
            className="w-full rounded-xl bg-slate-50 border border-slate-200 px-4 py-2.5 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-violet-500/20 focus:border-violet-500 transition-colors"
            value={apiUrl}
            onChange={(e) => setApiUrl(e.target.value)}
          />
          <p className="text-[11px] text-slate-500">
            Overrides the built-in default endpoint.
          </p>
        </div>

        <div className="space-y-1.5">
          <label className="block text-xs uppercase tracking-wide font-semibold text-slate-500">
            Coaching Model
          </label>
          <input
            className="w-full rounded-xl bg-slate-50 border border-slate-200 px-4 py-2.5 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-violet-500/20 focus:border-violet-500 transition-colors"
            value={model}
            onChange={(e) => setModel(e.target.value)}
          />
          <p className="text-[11px] text-slate-500">
            Model available on your local Ollama or OpenRouter instance.
          </p>
        </div>

        <div className="flex items-center gap-3 pt-2">
          <Button onClick={handleSave}>Save Preferences</Button>
          {saved ? (
            <span className="text-xs font-semibold text-emerald-600 bg-emerald-50 border border-emerald-200 px-2.5 py-1 rounded-full">
              Preferences Saved.
            </span>
          ) : null}
        </div>
      </Card>
    </div>
  );
}
