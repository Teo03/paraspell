// interface Stats {
//   words: number | null
//   errors: number | null
//   time: number | null
// }

// interface StatsRowProps {
//   stats: Stats
//   loading: boolean
// }

// export function StatsRow({ stats, loading }: StatsRowProps) {
//   return (
//     <div className="grid grid-cols-3 gap-3">
//       <div className="rounded-lg border p-3 text-center">
//         <p className="text-xs text-muted-foreground mb-1">Words Checked</p>
//         <p className="text-xl font-semibold">{loading ? "—" : (stats.words ?? "—")}</p>
//       </div>
//       <div className="rounded-lg border p-3 text-center">
//         <p className="text-xs text-muted-foreground mb-1">Errors Found</p>
//         <p className={`text-xl font-semibold ${!loading && stats.errors !== null && stats.errors > 0 ? "text-red-500" : ""}`}>
//           {loading ? "—" : (stats.errors ?? "—")}
//         </p>
//       </div>
//       <div className="rounded-lg border p-3 text-center">
//         <p className="text-xs text-muted-foreground mb-1">Processing Time</p>
//         <p className="text-xl font-semibold">
//           {loading ? "—" : (stats.time !== null ? `${stats.time}s` : "—")}
//         </p>
//       </div>
//     </div>
//   )
// }

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
  const cards = [
    { label: "WORDS CHECKED", value: loading ? "—" : (stats.words ?? "—"), color: "text-primary" },
    {
      label: "ERRORS FOUND",
      value: loading ? "—" : (stats.errors ?? "—"),
      color: !loading && stats.errors !== null && stats.errors > 0 ? "text-destructive" : "text-primary"
    },
    {
      label: "PROCESSING TIME",
      value: loading ? "—" : (stats.time !== null ? `${stats.time}s` : "—"),
      color: "text-primary"
    },
  ]

  return (
    <div className="grid grid-cols-3 gap-3">
      {cards.map((card, i) => (
        <div key={i} className="cyber-border bg-card p-3 text-center relative overflow-hidden">
          {/* Corner accents */}
          <span className="absolute top-0 left-0 w-2 h-2 border-t border-l border-primary" />
          <span className="absolute top-0 right-0 w-2 h-2 border-t border-r border-primary" />
          <span className="absolute bottom-0 left-0 w-2 h-2 border-b border-l border-primary" />
          <span className="absolute bottom-0 right-0 w-2 h-2 border-b border-r border-primary" />
          <p
            className="text-xs tracking-widest uppercase mb-2"
            style={{ color: "var(--cyan-dim)", fontFamily: "'Share Tech Mono', monospace" }}
          >
            {card.label}
          </p>
          <p
            className={`text-2xl font-bold ${card.color} glow-text`}
            style={{ fontFamily: "'Share Tech Mono', monospace" }}
          >
            {card.value}
          </p>
        </div>
      ))}
    </div>
  )
}