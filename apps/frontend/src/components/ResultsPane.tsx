import React, { useState, useRef, useEffect } from "react";
import type { Correction } from "../App";

interface Stats {
  words: number | null;
  errors: number | null;
  time: number | null;
}

interface ResultsPaneProps {
  loading: boolean;
  stats: Stats;
  text: string;
  corrections: Correction[];
  onApplyCorrection: (offset: number, newWord: string) => void;
  onIgnore: (offset: number) => void;
  onApplyAll: () => void;
  onExport: () => void;
  onReset: () => void;
}

interface PopoverState {
  offset: number;
  x: number;
  y: number;
}

export function ResultsPane({
  loading,
  stats,
  text,
  corrections,
  onApplyCorrection,
  onIgnore,
  onApplyAll,
  onExport,
  onReset,
}: ResultsPaneProps) {
  const [popover, setPopover] = useState<PopoverState | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setPopover(null);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  if (loading) {
    return (
      <div className="cyber-border bg-card p-4 space-y-3 relative overflow-hidden">
        <span className="absolute top-0 left-0 w-2 h-2 border-t border-l border-primary" />
        <span className="absolute top-0 right-0 w-2 h-2 border-t border-r border-primary" />
        <span className="absolute bottom-0 left-0 w-2 h-2 border-b border-l border-primary" />
        <span className="absolute bottom-0 right-0 w-2 h-2 border-b border-r border-primary" />
        <p
          className="text-xs tracking-widest text-primary animate-pulse"
          style={{ fontFamily: "'Share Tech Mono', monospace" }}
        >
          ANALYZING...
        </p>
        <div className="h-2 bg-primary/20 rounded-none animate-pulse w-3/4" />
        <div className="h-2 bg-primary/20 rounded-none animate-pulse w-full" />
        <div className="h-2 bg-primary/20 rounded-none animate-pulse w-5/6" />
        <div className="h-2 bg-primary/20 rounded-none animate-pulse w-2/3" />
        <div className="h-2 bg-primary/20 rounded-none animate-pulse w-4/5" />
      </div>
    );
  }

  const renderHighlightedText = () => {
    if (!text) return null;
    const sorted = [...corrections].sort((a, b) => a.offset - b.offset);
    const segments: React.ReactElement[] = [];
    let cursor = 0;

    for (const correction of sorted) {
      const { offset, original } = correction;
      if (offset > cursor) {
        segments.push(
          <span key={`plain-${cursor}`}>{text.slice(cursor, offset)}</span>,
        );
      }
      const isOpen = popover?.offset === offset;
      segments.push(
        <span
          key={`error-${offset}`}
          onClick={(e) => {
            e.stopPropagation();
            if (isOpen) {
              setPopover(null);
            } else {
              const rect = (e.target as HTMLElement).getBoundingClientRect();
              const containerRect =
                containerRef.current?.getBoundingClientRect();
              setPopover({
                offset,
                x: rect.left - (containerRect?.left ?? 0),
                y: rect.bottom - (containerRect?.top ?? 0) + 4,
              });
            }
          }}
          style={{
            textDecoration: "underline",
            textDecorationStyle: "wavy",
            textDecorationColor: "var(--destructive, #ef4444)",
            cursor: "pointer",
            backgroundColor: isOpen ? "rgba(239,68,68,0.12)" : "transparent",
            borderRadius: "2px",
            padding: "0 1px",
          }}
        >
          {original}
        </span>,
      );
      cursor = offset + original.length;
    }

    if (cursor < text.length) {
      segments.push(<span key={`plain-end`}>{text.slice(cursor)}</span>);
    }
    return segments;
  };

  const activeCorrection = corrections.find(
    (c) => c.offset === popover?.offset,
  );

  return (
    <div
      className="flex flex-col gap-3 h-full"
      style={{ fontFamily: "'Share Tech Mono', monospace" }}
    >
      {/* Output pane */}
      <div
        ref={containerRef}
        className="cyber-border bg-card p-4 flex-1 relative overflow-hidden"
      >
        <span className="absolute top-0 left-0 w-2 h-2 border-t border-l border-primary" />
        <span className="absolute top-0 right-0 w-2 h-2 border-t border-r border-primary" />
        <span className="absolute bottom-0 left-0 w-2 h-2 border-b border-l border-primary" />
        <span className="absolute bottom-0 right-0 w-2 h-2 border-b border-r border-primary" />

        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xs tracking-widest uppercase text-primary glow-text">
            // Output
          </h2>
          {corrections.length > 0 && (
            <button
              onClick={onApplyAll}
              className="text-xs tracking-widest uppercase px-3 py-1 border border-primary text-primary hover:bg-primary hover:text-primary-foreground transition-all duration-200 glow"
            >
              ✓ Apply All
            </button>
          )}
        </div>

        {stats.errors === 0 && corrections.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-3 py-8 text-center">
            <div className="w-14 h-14 border border-green-500 flex items-center justify-center">
              <svg
                className="w-7 h-7 text-green-500"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"
                />
              </svg>
            </div>
            <p className="text-sm tracking-widest uppercase text-green-500">
              No Errors Detected
            </p>
            <p className="text-xs text-muted-foreground tracking-wider">
              All systems nominal.
            </p>
          </div>
        ) : (
          <div
            className="text-sm leading-relaxed text-foreground whitespace-pre-wrap"
            style={{ fontFamily: "'Share Tech Mono', monospace" }}
          >
            {renderHighlightedText()}
          </div>
        )}

        {/* Popover */}
        {popover && activeCorrection && (
          <div
            style={{
              position: "absolute",
              left: popover.x,
              top: popover.y,
              zIndex: 50,
              minWidth: "160px",
            }}
            className="cyber-border bg-card border border-primary shadow-lg"
          >
            {activeCorrection.suggestions.length > 0 ? (
              <div>
                <p className="text-xs tracking-widest uppercase text-muted-foreground px-3 pt-2 pb-1">
                  Suggestions
                </p>
                {activeCorrection.suggestions.slice(0, 5).map((s, i) => (
                  <button
                    key={i}
                    onClick={() => {
                      onApplyCorrection(activeCorrection.offset, s.word);
                      setPopover(null);
                    }}
                    className="w-full text-left px-3 py-1.5 text-sm text-foreground hover:bg-primary hover:text-primary-foreground transition-colors"
                  >
                    {s.word}
                  </button>
                ))}
              </div>
            ) : (
              <p className="text-xs text-muted-foreground px-3 py-2">
                No suggestions
              </p>
            )}
            <div className="border-t border-border">
              <button
                onClick={() => {
                  onIgnore(activeCorrection.offset);
                  setPopover(null);
                }}
                className="w-full text-left px-3 py-1.5 text-xs tracking-widest uppercase text-destructive hover:bg-destructive/10 transition-colors"
              >
                ✕ Ignore
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Summary strip (5.2.4) */}
      {corrections.length > 0 && (
        <div className="cyber-border bg-card border border-primary/40 relative overflow-hidden">
          <span className="absolute top-0 left-0 w-2 h-2 border-t border-l border-primary" />
          <span className="absolute top-0 right-0 w-2 h-2 border-t border-r border-primary" />
          <span className="absolute bottom-0 left-0 w-2 h-2 border-b border-l border-primary" />
          <span className="absolute bottom-0 right-0 w-2 h-2 border-b border-r border-primary" />

          <div className="flex items-center justify-between px-3 py-2 border-b border-border">
            <p className="text-xs tracking-widest uppercase text-primary">
              // Errors ({corrections.length})
            </p>
            <button
              onClick={onApplyAll}
              className="text-xs tracking-widest uppercase px-3 py-1 border border-primary text-primary hover:bg-primary hover:text-primary-foreground transition-all duration-200 glow"
            >
              ✓ Apply All
            </button>
          </div>

          <div className="max-h-32 overflow-y-auto">
            {corrections.map((c) => (
              <div
                key={c.offset}
                className="flex items-center justify-between px-3 py-1.5 border-b border-border/50 last:border-b-0 hover:bg-muted/20"
              >
                <div className="flex items-center gap-2">
                  <span className="text-xs text-destructive font-bold">
                    {c.original}
                  </span>
                  {c.suggestions.length > 0 && (
                    <>
                      <span className="text-xs text-muted-foreground">→</span>
                      <span className="text-xs text-primary">
                        {c.suggestions[0].word}
                      </span>
                    </>
                  )}
                </div>
                <div className="flex gap-2">
                  {c.suggestions.length > 0 && (
                    <button
                      onClick={() =>
                        onApplyCorrection(c.offset, c.suggestions[0].word)
                      }
                      className="text-xs text-primary hover:text-primary/70 transition-colors px-1"
                    >
                      ✓
                    </button>
                  )}
                  <button
                    onClick={() => onIgnore(c.offset)}
                    className="text-xs text-destructive hover:text-destructive/70 transition-colors px-1"
                  >
                    ✕
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Action buttons */}
      <div className="flex gap-3">
        <button
          onClick={onExport}
          className="flex-1 py-2 text-xs font-bold tracking-widest uppercase border border-primary text-primary hover:bg-primary hover:text-primary-foreground transition-all duration-200 glow"
        >
          ↓ Export
        </button>
        <button
          onClick={onReset}
          className="py-2 px-4 text-xs font-bold tracking-widest uppercase border border-destructive text-destructive hover:bg-destructive hover:text-white transition-all duration-200"
        >
          ✕ Reset
        </button>
      </div>
    </div>
  );
}
