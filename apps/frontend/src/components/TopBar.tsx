// export function TopBar() {
//   return (
//     <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
//       <div className="px-6 h-14 flex flex-col justify-center">
//         <span className="text-lg font-semibold tracking-tight leading-none">ParaSpell</span>
//         <span className="text-xs text-muted-foreground leading-none mt-0.5">Parallel Spell Checker</span>
//       </div>
//     </header>
//   )
// }


export function TopBar() {
  return (
    <header className="sticky top-0 z-50 w-full border-b border-border bg-background/90 backdrop-blur-md">
      <div className="px-6 h-14 flex items-center justify-between">
        <div className="flex items-center gap-3">
          {/* Logo mark */}
          <div className="w-7 h-7 border border-primary flex items-center justify-center glow">
            <div className="w-3 h-3 bg-primary" style={{ clipPath: "polygon(50% 0%, 100% 100%, 0% 100%)" }} />
          </div>
          <div>
            <span
              className="text-xl font-bold tracking-widest uppercase glow-text"
              style={{ fontFamily: "'Share Tech Mono', monospace", color: "var(--cyan-glow)" }}
            >
              ParaSpell
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs tracking-widest uppercase" style={{ color: "var(--cyan-dim)", fontFamily: "'Share Tech Mono', monospace" }}>
            Parallel Spell Checker
          </span>
          {/* Status dot */}
          <span className="w-2 h-2 rounded-full bg-primary animate-pulse glow" />
        </div>
      </div>
    </header>
  )
}