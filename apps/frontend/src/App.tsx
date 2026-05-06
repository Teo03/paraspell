import { useState } from "react"
import { FileUploadZone } from "@/components/FileUploadZone"

function App() {
  const [file, setFile] = useState<File | null>(null)

  return (
    <main className="min-h-svh flex flex-col items-center justify-center gap-6 p-6">
      <div className="text-center">
        <h1 className="text-4xl font-semibold tracking-tight text-foreground">
          ParaSpell
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Parallel Spell Checker
        </p>
      </div>

      <div className="w-full max-w-xl">
        <FileUploadZone onFileSelect={(f) => setFile(f)} />
        {file && (
          <p className="mt-3 text-xs text-center text-muted-foreground">
            Ready to check: <span className="text-foreground font-medium">{file.name}</span>
          </p>
        )}
      </div>
    </main>
  )
}

export default App
