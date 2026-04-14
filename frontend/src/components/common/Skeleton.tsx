interface SkeletonProps {
  className?: string;
}

export function Skeleton({ className = "" }: SkeletonProps) {
  return (
    <div
      className={`rounded bg-white/5 ${className}`}
      style={{
        backgroundImage: "linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.04) 50%, transparent 100%)",
        backgroundSize: "200% 100%",
        animation: "shimmer 1.5s infinite",
      }}
    />
  );
}

export function SkeletonCard() {
  return (
    <div className="rounded-xl border border-border bg-surface p-4 space-y-3">
      <Skeleton className="h-4 w-1/3" />
      <Skeleton className="h-8 w-1/2" />
      <Skeleton className="h-3 w-2/3" />
    </div>
  );
}

export function SkeletonRow() {
  return (
    <div className="flex items-center gap-4 py-2">
      <Skeleton className="h-4 w-12" />
      <Skeleton className="h-4 w-32" />
      <Skeleton className="h-4 w-16 ml-auto" />
    </div>
  );
}
