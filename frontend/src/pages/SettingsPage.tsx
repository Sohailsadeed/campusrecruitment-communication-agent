import { useState } from "react";
import Card from "../components/Common/Card";
import Button from "../components/Common/Button";

export default function SettingsPage() {
  const [apiUrl, setApiUrl] = useState(
    (import.meta.env.VITE_API_URL as string | undefined) ||
      "http://localhost:8000"
  );
  const [model, setModel] = useState("llama3.2");
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
        <h1 className="text-3xl font-bold tracking-tight">Settings</h1>
        <p className="text-slate-400">Tune SpeakFlow to your environment.</p>
      </div>

      <Card className="space-y-5">
        <div className="space-y-1.5">
          <label className="block text-xs uppercase tracking-wide text-slate-400">
            Backend API URL
          </label>
          <input
            className="w-full rounded-xl bg-black/30 border border-white/10 px-4 py-2.5 text-sm focus:outline-none focus:border-primary-500/60"
            value={apiUrl}
            onChange={(e) => setApiUrl(e.target.value)}
          />
          <p className="text-[11px] text-slate-500">
            Overrides the built-in default. Rebuild the frontend to pick up
            env-level changes.
          </p>
        </div>

        <div className="space-y-1.5">
          <label className="block text-xs uppercase tracking-wide text-slate-400">
            Coaching model
          </label>
          <input
            className="w-full rounded-xl bg-black/30 border border-white/10 px-4 py-2.5 text-sm focus:outline-none focus:border-primary-500/60"
            value={model}
            onChange={(e) => setModel(e.target.value)}
          />
          <p className="text-[11px] text-slate-500">
            Must be a model available to your local Ollama instance.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Button onClick={handleSave}>Save preferences</Button>
          {saved ? (
            <span className="text-xs text-emerald-300">Saved locally.</span>
          ) : null}
        </div>
      </Card>
    </div>
  );
}
