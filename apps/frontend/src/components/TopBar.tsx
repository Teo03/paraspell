export function TopBar() {
  return (
    <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="px-6 h-14 flex flex-col justify-center">
        <span className="text-lg font-semibold tracking-tight leading-none">ParaSpell</span>
        <span className="text-xs text-muted-foreground leading-none mt-0.5">Parallel Spell Checker</span>
      </div>
    </header>
  )
}