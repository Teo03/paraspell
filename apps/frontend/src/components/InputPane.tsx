import { useState } from "react";
import { FileUploadZone } from "@/components/FileUploadZone";

type Tab = "paste" | "upload";

const Spinner = () => (
  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z" />
  </svg>
);

interface InputPaneProps {
  loading: boolean;
  onCheck: (text: string, file?: File | null) => void;
  fullHeight?: boolean;
  onFileSelect?: (file: File | null) => void;
}

export function InputPane({
  loading,
  onCheck,
  onFileSelect,
  fullHeight = false,
}: InputPaneProps) {
  const [activeTab, setActiveTab] = useState<Tab>("paste");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);

  const wordCount = text.trim() === "" ? 0 : text.trim().split(/\s+/).length;

  const tabClass = (active: boolean) =>
    `flex-1 py-2 text-xs tracking-widest uppercase transition-all duration-200 focus:outline-none
    ${active
      ? "bg-primary text-primary-foreground glow"
      : "bg-transparent text-muted-foreground hover:text-primary border-r border-border last:border-r-0"
    }`;

  const checkBtnClass = `
    px-5 py-1.5 text-xs font-bold tracking-widest uppercase
    bg-primary text-primary-foreground
    hover:bg-primary/80 transition-all duration-200
    disabled:opacity-30 disabled:cursor-not-allowed
    flex items-center gap-2 glow
  `;

  return (
    <div className="w-full flex flex-col" style={{ fontFamily: "'Share Tech Mono', monospace" }}>

      {/* Tab Toggle */}
      <div className="flex border border-border overflow-hidden mb-4" role="tablist">
        <button
          role="tab"
          aria-selected={activeTab === "paste"}
          onClick={() => setActiveTab("paste")}
          onKeyDown={(e) => e.key === "ArrowRight" && setActiveTab("upload")}
          className={tabClass(activeTab === "paste")}
        >
          Paste Text
        </button>
        <button
          role="tab"
          aria-selected={activeTab === "upload"}
          onClick={() => setActiveTab("upload")}
          onKeyDown={(e) => e.key === "ArrowLeft" && setActiveTab("paste")}
          className={tabClass(activeTab === "upload")}
        >
          Upload File
        </button>
      </div>

      {/* Paste Text Tab */}
      {activeTab === "paste" && (
        <div className="cyber-border bg-card overflow-hidden flex flex-col">
          <textarea
            className={`w-full p-4 text-sm bg-transparent text-foreground resize-none focus:outline-none placeholder:text-muted-foreground ${fullHeight ? "h-[40vh]" : "h-64"}`}
            style={{ fontFamily: "'Share Tech Mono', monospace" }}
            placeholder="// paste or type your text here..."
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="px-4 py-2 border-t border-border flex items-center justify-between bg-muted/30">
            <span className="text-xs text-muted-foreground tracking-widest">
              {String(wordCount).padStart(4, "0")} WORDS
            </span>
            <button
              disabled={wordCount === 0 || loading}
              onClick={() => onCheck(text)}
              className={checkBtnClass}
            >
              {loading ? <><Spinner /> Processing...</> : "▶ Run Check"}
            </button>
          </div>
        </div>
      )}

      {/* Upload File Tab */}
      {activeTab === "upload" && (
        <div className="cyber-border bg-card overflow-hidden flex flex-col">
          <div className={`p-4 flex flex-col justify-center ${fullHeight ? "min-h-[40vh]" : "min-h-[200px]"}`}>
            <FileUploadZone
              onFileSelect={(f) => {
                setFile(f);
                onFileSelect?.(f);
              }}
            />
            {file && (
              <p className="mt-3 text-xs text-center text-muted-foreground tracking-widest">
                LOADED: <span className="text-primary">{file.name}</span>
              </p>
            )}
          </div>
          <div className="px-4 py-2 border-t border-border flex items-center justify-between bg-muted/30">
            <span className="text-xs text-muted-foreground tracking-widest">
              {file ? "1 FILE QUEUED" : "NO FILE"}
            </span>
            <button
              disabled={!file || loading}
              onClick={() => onCheck("", file)}
              className={checkBtnClass}
            >
              {loading ? <><Spinner /> Processing...</> : "▶ Run Check"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}