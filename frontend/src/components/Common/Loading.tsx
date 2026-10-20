interface LoadingProps {
  label?: string;
}

export default function Loading({ label = "Loading..." }: LoadingProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-slate-300">
      <div className="w-10 h-10 border-4 border-primary-500/30 border-t-primary-400 rounded-full animate-spin" />
      <p className="text-sm">{label}</p>
    </div>
  );
}
