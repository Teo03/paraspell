import { useState } from "react"
import { TopBar } from "@/components/TopBar"
import { StatsRow } from "@/components/StatsRow"
import { InputPane } from "@/components/InputPane"
import { ResultsPane } from "@/components/ResultsPane"

interface Stats {
  words: number | null
  errors: number | null
  time: number | null
}

function App() {
  const [loading, setLoading] = useState(false)
  const [hasChecked, setHasChecked] = useState(false)
  const [checkedText, setCheckedText] = useState("")
  const [stats, setStats] = useState<Stats>({ words: null, errors: null, time: null })
  const [resetKey, setResetKey] = useState(0)

  const handleCheck = (text: string, _file: File | null) => {
    const wordCount = text.trim() === "" ? 0 : text.trim().split(/\s+/).length
    setLoading(true)
    setHasChecked(true)
    setCheckedText(text)
    setStats({ words: null, errors: null, time: null })
    setTimeout(() => {
      setLoading(false)
      setStats({ words: wordCount, errors: 0, time: 0.5 })
    }, 3000)
  }

  const handleExport = () => {
    const blob = new Blob([checkedText], { type: "text/plain" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = "corrected.txt"
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleReset = () => {
    setLoading(false)
    setHasChecked(false)
    setCheckedText("")
    setStats({ words: null, errors: null, time: null })
    setResetKey((k) => k + 1)
  }

  return (
    <div className="min-h-svh flex flex-col bg-background">
      <TopBar />

      <main className="flex-1 flex flex-col p-6 gap-6">
        <StatsRow stats={stats} loading={loading} />

        <div className="flex flex-col md:flex-row gap-6 flex-1">
          <div className={`w-full ${hasChecked ? "md:w-1/2" : "md:max-w-xl md:mx-auto"}`}>
            <InputPane key={resetKey} loading={loading} onCheck={handleCheck} />
          </div>

          {hasChecked && (
            <div className="w-full md:w-1/2">
              <ResultsPane
                loading={loading}
                stats={stats}
                text={checkedText}
                onExport={handleExport}
                onReset={handleReset}
              />
            </div>
          )}
        </div>
      </main>
    </div>
  )
}

export default App