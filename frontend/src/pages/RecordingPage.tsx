import RecordingSession from "../components/Recording/RecordingSession";

export default function RecordingPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Recording studio</h1>
        <p className="text-slate-400">
          Hit the record button and speak as if you were in front of your real
          audience.
        </p>
      </div>
      <RecordingSession />
    </div>
  );
}
