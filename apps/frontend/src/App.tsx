import { useState } from "react";
import { TopBar } from "@/components/TopBar";
import { StatsRow } from "@/components/StatsRow";
import { InputPane } from "@/components/InputPane";
import { ResultsPane } from "@/components/ResultsPane";

// Vite inlines `import.meta.env.VITE_*` at build time. Set
// VITE_API_BASE_URL in your hosting provider (Vercel project settings,
// or apps/frontend/.env.production) so production builds hit the right
// backend. Falls back to the docker-compose default for local dev.
const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ||
  "http://localhost:8000";

interface Stats {
  words: number | null;
  errors: number | null;
  time: number | null;
}

export interface Suggestion {
  word: string;
  score: number;
}

export interface Correction {
  original: string;
  offset: number;
  suggestions: Suggestion[];
}

function App() {
  const [loading, setLoading] = useState(false);
  const [hasChecked, setHasChecked] = useState(false);
  const [checkedText, setCheckedText] = useState("");
  const [stats, setStats] = useState<Stats>({
    words: null,
    errors: null,
    time: null,
  });
  const [corrections, setCorrections] = useState<Correction[]>([]);
  const [resetKey, setResetKey] = useState(0);
  const [originalFileName, setOriginalFileName] = useState<string | null>(null);

  const handleCheck = async (text: string, file?: File | null) => {
    setLoading(true);
    setHasChecked(true);
    setCheckedText(text);
    setStats({ words: null, errors: null, time: null });
    setCorrections([]);

    const start = Date.now();

    try {
      let res: Response;

      if (file) {
        const formData = new FormData();
        formData.append("file", file);
        res = await fetch(`${API_BASE_URL}/check/file`, {
          method: "POST",
          body: formData,
        });
      } else {
        res = await fetch(`${API_BASE_URL}/check/text`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text }),
        });
      }

      const data = await res.json();
      const elapsed = ((Date.now() - start) / 1000).toFixed(1);

      setStats({
        words: data.word_count,
        errors: data.error_count,
        time: data.processing_time ?? parseFloat(elapsed),
      });
      setCheckedText(data.extracted_text || text);
      setCorrections(data.corrections ?? []);
    } catch (err) {
      console.error("API error:", err);
      setStats({ words: 0, errors: 0, time: 0 });
    } finally {
      setLoading(false);
    }
  };

const handleApplyCorrection = (offset: number, newWord: string) => {
  const correction = corrections.find((c) => c.offset === offset);
  if (!correction) return;

  const before = checkedText.slice(0, offset);
  const after = checkedText.slice(offset + correction.original.length);
  const newText = before + newWord + after;

  // Recalculate offsets for remaining corrections
  const diff = newWord.length - correction.original.length;
  const updatedCorrections = corrections
    .filter((c) => c.offset !== offset)
    .map((c) => ({
      ...c,
      offset: c.offset > offset ? c.offset + diff : c.offset,
    }));

  setCheckedText(newText);
  setCorrections(updatedCorrections);
  setStats((prev) => ({
    ...prev,
    errors: prev.errors !== null ? Math.max(0, prev.errors - 1) : null,
  }));
};

  const handleIgnore = (offset: number) => {
    setCorrections((prev) => prev.filter((c) => c.offset !== offset));
    setStats((prev) => ({
      ...prev,
      errors: prev.errors !== null ? Math.max(0, prev.errors - 1) : null,
    }));
  };

  const handleApplyAll = () => {
    let text = checkedText;
    const sorted = [...corrections].sort((a, b) => b.offset - a.offset);
    for (const c of sorted) {
      if (c.suggestions.length > 0) {
        const before = text.slice(0, c.offset);
        const after = text.slice(c.offset + c.original.length);
        text = before + c.suggestions[0].word + after;
      }
    }
    setCheckedText(text);
    setCorrections([]);
    setStats((prev) => ({ ...prev, errors: 0 }));
  };

  const handleExport = () => {
    const baseName = originalFileName
      ? originalFileName.replace(/\.[^/.]+$/, "")
      : "corrected";
    const blob = new Blob([checkedText], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `corrected_${baseName}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleReset = () => {
    setLoading(false);
    setHasChecked(false);
    setCheckedText("");
    setStats({ words: null, errors: null, time: null });
    setCorrections([]);
    setResetKey((k) => k + 1);
  };

  return (
    <div className="min-h-svh flex flex-col bg-background">
      <TopBar />

      <main className="flex-1 flex flex-col items-center p-6 gap-6">

        {/* Input — always centered at 80% */}
        <div className="w-[80%]">
          <InputPane
            key={resetKey}
            loading={loading}
            onCheck={handleCheck}
            onFileSelect={(file) => setOriginalFileName(file?.name ?? null)}
            fullHeight={!hasChecked}
          />
        </div>

        {/* Stats — appears below input after first check */}
        {hasChecked && (
          <div className="w-[80%]">
            <StatsRow stats={stats} loading={loading} />
          </div>
        )}

        {/* Results — appears below stats after first check */}
        {hasChecked && (
          <div className="w-[80%]">
            <ResultsPane
              loading={loading}
              stats={stats}
              text={checkedText}
              corrections={corrections}
              onApplyCorrection={handleApplyCorrection}
              onIgnore={handleIgnore}
              onApplyAll={handleApplyAll}
              onExport={handleExport}
              onReset={handleReset}
            />
          </div>
        )}

      </main>
    </div>
  );
}

export default App;