import { useState } from "react"
import { FileUploadZone } from "@/components/FileUploadZone"

type Tab = "paste" | "upload"

function App() {
  const [file, setFile] = useState<File | null>(null)
  const [activeTab, setActiveTab] = useState<Tab>("paste")
  const [text, setText] = useState("")
  const [loading, setLoading] = useState(false)
  const [stats, setStats] = useState<{ words: number | null; errors: number | null; time: number | null }>({
    words: null,
    errors: null,
    time: null,
  })

  const wordCount = text.trim() === "" ? 0 : text.trim().split(/\s+/).length

  // Temporary test handler so we can verify loading states work
  const handleCheck = () => {
    setLoading(true)
    setStats({ words: null, errors: null, time: null })
    setTimeout(() => setLoading(false), 3000)
  }

  return (
    <div className="min-h-svh flex flex-col bg-background">
      {/* Top Bar */}
      <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="px-6 h-14 flex flex-col justify-center">
          <span className="text-lg font-semibold tracking-tight leading-none">ParaSpell</span>
          <span className="text-xs text-muted-foreground leading-none mt-0.5">Parallel Spell Checker</span>
        </div>
      </header>

      <main className="flex-1 flex flex-col items-center p-6 gap-6">

        {/* Stats Row */}
        <div className="w-full max-w-xl grid grid-cols-3 gap-3 mb-2">
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

        <div className="w-full max-w-xl">

          {/* Tab Toggle */}
          <div className="flex rounded-lg border overflow-hidden mb-4" role="tablist">
            <button
              role="tab"
              aria-selected={activeTab === "paste"}
              onClick={() => setActiveTab("paste")}
              onKeyDown={(e) => e.key === "ArrowRight" && setActiveTab("upload")}
              className={`flex-1 py-2 text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-ring
                ${activeTab === "paste"
                  ? "bg-primary text-primary-foreground"
                  : "bg-background text-muted-foreground hover:text-foreground hover:bg-muted"}`}
            >
              Paste Text
            </button>
            <button
              role="tab"
              aria-selected={activeTab === "upload"}
              onClick={() => setActiveTab("upload")}
              onKeyDown={(e) => e.key === "ArrowLeft" && setActiveTab("paste")}
              className={`flex-1 py-2 text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-ring
                ${activeTab === "upload"
                  ? "bg-primary text-primary-foreground"
                  : "bg-background text-muted-foreground hover:text-foreground hover:bg-muted"}`}
            >
              Upload File
            </button>
          </div>

          {/* Tab Content */}
          {activeTab === "paste" && (
            <div className="rounded-lg border overflow-hidden">
              <textarea
                className="w-full h-64 p-4 font-mono text-sm bg-background text-foreground resize-none focus:outline-none placeholder:text-muted-foreground"
                placeholder="Paste or type your text here..."
                value={text}
                onChange={(e) => setText(e.target.value)}
              />
              <div className="px-4 py-2 border-t flex items-center justify-between">
                <span className="text-xs text-muted-foreground">
                  {wordCount} {wordCount === 1 ? "word" : "words"}
                </span>
                <button
                  disabled={wordCount === 0 || loading}
                  onClick={handleCheck}
                  className="px-4 py-1.5 text-sm font-medium rounded-md bg-primary text-primary-foreground
                    hover:bg-primary/90 transition-colors
                    disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                >
                  {loading ? (
                    <>
                      <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z" />
                      </svg>
                      Checking...
                    </>
                  ) : "Check Spelling"}
                </button>
              </div>
            </div>
          )}

          {activeTab === "upload" && (
            <div className="rounded-lg border overflow-hidden">
              <div className="p-4">
                <FileUploadZone onFileSelect={(f) => setFile(f)} />
                {file && (
                  <p className="mt-3 text-xs text-center text-muted-foreground">
                    Ready to check: <span className="text-foreground font-medium">{file.name}</span>
                  </p>
                )}
              </div>
              <div className="px-4 py-2 border-t flex items-center justify-between">
                <span className="text-xs text-muted-foreground">
                  {file ? "1 file selected" : "No file selected"}
                </span>
                <button
                  disabled={!file || loading}
                  onClick={handleCheck}
                  className="px-4 py-1.5 text-sm font-medium rounded-md bg-primary text-primary-foreground
                    hover:bg-primary/90 transition-colors
                    disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                >
                  {loading ? (
                    <>
                      <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z" />
                      </svg>
                      Checking...
                    </>
                  ) : "Check Spelling"}
                </button>
              </div>
            </div>
          )}

          {/* Results Skeleton */}
          {loading && (
            <div className="mt-4 rounded-lg border p-4 space-y-3">
              <div className="h-3 bg-muted rounded animate-pulse w-3/4" />
              <div className="h-3 bg-muted rounded animate-pulse w-full" />
              <div className="h-3 bg-muted rounded animate-pulse w-5/6" />
              <div className="h-3 bg-muted rounded animate-pulse w-2/3" />
            </div>
          )}

        </div>
      </main>
    </div>
  )
}

export default App