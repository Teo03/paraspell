import { useState } from 'react'
import { Button } from '@/components/ui/button'

function App() {
  const [count, setCount] = useState(0)

  return (
    <main className="min-h-svh flex flex-col items-center justify-center gap-6 p-6 text-center">
      <div>
        <h1 className="text-4xl font-semibold tracking-tight text-foreground">
          ParaSpell
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Parallel Spell Checker — frontend hello world
        </p>
      </div>

      <div className="flex flex-col items-center gap-3">
        <Button onClick={() => setCount((c) => c + 1)}>
          Clicked {count} times
        </Button>
        <p className="text-xs text-muted-foreground">
          Tailwind v4 + shadcn/ui Button is rendering.
        </p>
      </div>
    </main>
  )
}

export default App
