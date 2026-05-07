interface Stats {
  words: number | null
  errors: number | null
  time: number | null
}

interface StatsRowProps {
  stats: Stats
  loading: boolean
}

export function StatsRow({ stats, loading }: StatsRowProps) {
  return (
    <div className="grid grid-cols-3 gap-3">
      <div className="rounded-lg border p-3 text-center">
        <p className="text-xs text-muted-foreground mb-1">Words Checked</p>
        <p className="text-xl font-semibold">{loading ? "—" : (stats.words ?? "—")}</p>
      </div>
      <div className="rounded-lg border p-3 text-center">
        <p className="text-xs text-muted-foreground mb-1">Errors Found</p>
        <p className={`text-xl font-semibold ${!loading && stats.errors !== null && stats.errors > 0 ? "text-red-500" : ""}`}>
          {loading ? "—" : (stats.errors ?? "—")}
        </p>
      </div>
      <div className="rounded-lg border p-3 text-center">
        <p className="text-xs text-muted-foreground mb-1">Processing Time</p>
        <p className="text-xl font-semibold">
          {loading ? "—" : (stats.time !== null ? `${stats.time}s` : "—")}
        </p>
      </div>
    </div>
  )
}