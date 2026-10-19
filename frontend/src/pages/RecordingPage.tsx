import RecordingSession from "../components/Recording/RecordingSession";

export default function RecordingPage() {
  return (
    <div className="space-y-6 max-w-7xl mx-auto px-4 sm:px-8 py-6">
      <div>
        <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-surface-container-high text-secondary font-label-numeric-sm text-[11px] font-medium mb-2">
          <span className="w-1.5 h-1.5 rounded-full bg-secondary animate-pulse" />
          Live Acoustic &amp; Optical Tracking
        </div>
        <h1 className="text-2xl sm:text-3xl font-bold text-on-surface tracking-tight font-headline-lg">
          JAM Recording Studio
        </h1>
        <p className="text-on-surface-variant text-sm mt-1">
          Spin a topic, take 10 seconds of prep, and speak uninterrupted for 60 seconds with live disfluency telemetry.
        </p>
      </div>
      <RecordingSession />
    </div>
  );
}
