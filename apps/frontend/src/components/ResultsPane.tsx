// interface Stats {
//   words: number | null
//   errors: number | null
//   time: number | null
// }

// interface ResultsPaneProps {
//   loading: boolean
//   stats: Stats
//   text: string
//   onExport: () => void
//   onReset: () => void
// }

// export function ResultsPane({ loading, stats, onExport, onReset }: ResultsPaneProps) {
//   if (loading) {
//     return (
//       <div className="rounded-lg border p-4 space-y-3">
//         <div className="h-3 bg-muted rounded animate-pulse w-3/4" />
//         <div className="h-3 bg-muted rounded animate-pulse w-full" />
//         <div className="h-3 bg-muted rounded animate-pulse w-5/6" />
//         <div className="h-3 bg-muted rounded animate-pulse w-2/3" />
//       </div>
//     )
//   }

//   return (
//     <div className="flex flex-col gap-3 h-full">
//       <div className="rounded-lg border p-4 flex-1">
//         <h2 className="text-sm font-semibold mb-3">Results</h2>
//         {stats.errors === 0 ? (
//           <div className="flex flex-col items-center justify-center gap-2 py-8 text-center">
//             <svg className="w-10 h-10 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
//               <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
//             </svg>
//             <p className="text-sm font-medium">No spelling errors found!</p>
//             <p className="text-xs text-muted-foreground">Your text looks great.</p>
//           </div>
//         ) : (
//           <p className="text-sm text-muted-foreground">Errors will be highlighted here.</p>
//         )}
//       </div>

//       {/* Action buttons */}
//       <div className="flex gap-3">
//         <button
//           onClick={onExport}
//           className="flex-1 py-2 text-sm font-medium rounded-md border border-primary text-primary
//             hover:bg-primary hover:text-primary-foreground transition-colors"
//         >
//           Export Corrected Text
//         </button>
//         <button
//           onClick={onReset}
//           className="py-2 px-4 text-sm font-medium rounded-md border border-destructive text-destructive
//             hover:bg-destructive hover:text-white transition-colors"
//         >
//           Clear / Reset
//         </button>
//       </div>
//     </div>
//   )
// }



interface Stats {
  words: number | null
  errors: number | null
  time: number | null
}

interface ResultsPaneProps {
  loading: boolean
  stats: Stats
  text: string
  onExport: () => void
  onReset: () => void
}

export function ResultsPane({ loading, stats, onExport, onReset }: ResultsPaneProps) {
  if (loading) {
    return (
      <div className="cyber-border bg-card p-4 space-y-3 relative overflow-hidden">
        <span className="absolute top-0 left-0 w-2 h-2 border-t border-l border-primary" />
        <span className="absolute top-0 right-0 w-2 h-2 border-t border-r border-primary" />
        <span className="absolute bottom-0 left-0 w-2 h-2 border-b border-l border-primary" />
        <span className="absolute bottom-0 right-0 w-2 h-2 border-b border-r border-primary" />
        <p className="text-xs tracking-widest text-primary animate-pulse" style={{ fontFamily: "'Share Tech Mono', monospace" }}>
          ANALYZING...
        </p>
        <div className="h-2 bg-primary/20 rounded-none animate-pulse w-3/4" />
        <div className="h-2 bg-primary/20 rounded-none animate-pulse w-full" />
        <div className="h-2 bg-primary/20 rounded-none animate-pulse w-5/6" />
        <div className="h-2 bg-primary/20 rounded-none animate-pulse w-2/3" />
        <div className="h-2 bg-primary/20 rounded-none animate-pulse w-4/5" />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3 h-full" style={{ fontFamily: "'Share Tech Mono', monospace" }}>
      <div className="cyber-border bg-card p-4 flex-1 relative overflow-hidden">
        {/* Corner accents */}
        <span className="absolute top-0 left-0 w-2 h-2 border-t border-l border-primary" />
        <span className="absolute top-0 right-0 w-2 h-2 border-t border-r border-primary" />
        <span className="absolute bottom-0 left-0 w-2 h-2 border-b border-l border-primary" />
        <span className="absolute bottom-0 right-0 w-2 h-2 border-b border-r border-primary" />

        <h2 className="text-xs tracking-widest uppercase text-primary mb-4 glow-text">// Output</h2>

        {stats.errors === 0 ? (
          <div className="flex flex-col items-center justify-center gap-3 py-8 text-center">
            <div className="w-14 h-14 border border-primary flex items-center justify-center glow">
              <svg className="w-7 h-7 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
              </svg>
            </div>
            <p className="text-sm tracking-widest uppercase text-primary glow-text">No Errors Detected</p>
            <p className="text-xs text-muted-foreground tracking-wider">All systems nominal.</p>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground tracking-wider">Errors will be highlighted here.</p>
        )}
      </div>

      {/* Action buttons */}
      <div className="flex gap-3">
        <button
          onClick={onExport}
          className="flex-1 py-2 text-xs font-bold tracking-widest uppercase border border-primary text-primary
            hover:bg-primary hover:text-primary-foreground transition-all duration-200 glow"
        >
          ↓ Export
        </button>
        <button
          onClick={onReset}
          className="py-2 px-4 text-xs font-bold tracking-widest uppercase border border-destructive text-destructive
            hover:bg-destructive hover:text-white transition-all duration-200"
        >
          ✕ Reset
        </button>
      </div>
    </div>
  )
}