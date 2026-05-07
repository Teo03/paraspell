import { useState } from "react"
import { FileUploadZone } from "@/components/FileUploadZone"

type Tab = "paste" | "upload"

const Spinner = () => (
  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z" />
  </svg>
)

interface InputPaneProps {
  loading: boolean
  onCheck: (text: string) => void
}

export function InputPane({ loading, onCheck }: InputPaneProps) {
  const [activeTab, setActiveTab] = useState<Tab>("paste")
  const [text, setText] = useState("")
  const [file, setFile] = useState<File | null>(null)

  const wordCount = text.trim() === "" ? 0 : text.trim().split(/\s+/).length

  return (
    <div className="w-full">

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

      {/* Paste Text Tab */}
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
              onClick={() => onCheck(text)}
              className="px-4 py-1.5 text-sm font-medium rounded-md bg-primary text-primary-foreground
                hover:bg-primary/90 transition-colors
                disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {loading ? <><Spinner /> Checking...</> : "Check Spelling"}
            </button>
          </div>
        </div>
      )}

      {/* Upload File Tab */}
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
              onClick={() => onCheck("")}
              className="px-4 py-1.5 text-sm font-medium rounded-md bg-primary text-primary-foreground
                hover:bg-primary/90 transition-colors
                disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {loading ? <><Spinner /> Checking...</> : "Check Spelling"}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}