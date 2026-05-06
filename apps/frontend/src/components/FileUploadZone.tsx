/**
 * FileUploadZone — drag-and-drop file upload component (FR-02)
 *
 * Checklist:
 * ✅ onDrop handler for drag-and-drop
 * ✅ File browser button as fallback
 * ✅ Display uploaded file name and size
 * ✅ Show accepted types and 20 MB limit
 */

import { useRef, useState, useCallback } from "react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"

const MAX_SIZE_MB = 20
const MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024
const ACCEPTED_TYPES = [".txt", ".docx", ".pdf"]
const ACCEPTED_MIME = [
  "text/plain",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/pdf",
]

interface FileUploadZoneProps {
  onFileSelect: (file: File) => void
  disabled?: boolean
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

export function FileUploadZone({ onFileSelect, disabled = false }: FileUploadZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [isDragging, setIsDragging] = useState(false)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [error, setError] = useState<string | null>(null)

  const validate = useCallback((file: File): string | null => {
    if (!ACCEPTED_MIME.includes(file.type) && !ACCEPTED_TYPES.some(ext => file.name.endsWith(ext))) {
      return `Unsupported file type. Please upload a ${ACCEPTED_TYPES.join(", ")} file.`
    }
    if (file.size > MAX_SIZE_BYTES) {
      return `File is too large. Maximum size is ${MAX_SIZE_MB} MB.`
    }
    return null
  }, [])

  const handleFile = useCallback((file: File) => {
    const err = validate(file)
    if (err) {
      setError(err)
      setSelectedFile(null)
      return
    }
    setError(null)
    setSelectedFile(file)
    onFileSelect(file)
  }, [validate, onFileSelect])

  // Drag handlers
  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    if (!disabled) setIsDragging(true)
  }
  const onDragLeave = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
  }
  const onDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    if (disabled) return
    const file = e.dataTransfer.files?.[0]
    if (file) handleFile(file)
  }

  // File browser fallback
  const onInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) handleFile(file)
    e.target.value = ""
  }

  const clearFile = () => {
    setSelectedFile(null)
    setError(null)
  }

  return (
    <div className="w-full flex flex-col gap-3">
      {/* Drop zone */}
      <div
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        onClick={() => !disabled && inputRef.current?.click()}
        className={cn(
          "relative flex flex-col items-center justify-center gap-3",
          "w-full min-h-[200px] rounded-xl border-2 border-dashed",
          "cursor-pointer transition-all duration-200 select-none",
          "bg-muted/40 hover:bg-muted/60",
          isDragging
            ? "border-primary bg-primary/5 scale-[1.01]"
            : "border-border hover:border-primary/50",
          disabled && "pointer-events-none opacity-50",
          selectedFile && "border-solid border-primary/40 bg-primary/5",
        )}
      >
        {/* Icon */}
        <div className={cn(
          "flex items-center justify-center w-12 h-12 rounded-full transition-colors",
          isDragging ? "bg-primary/10" : "bg-muted",
        )}>
          {selectedFile ? (
            // File icon when selected
            <svg className="w-6 h-6 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z" />
            </svg>
          ) : (
            // Upload icon
            <svg className="w-6 h-6 text-muted-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5m-13.5-9L12 3m0 0 4.5 4.5M12 3v13.5" />
            </svg>
          )}
        </div>

        {/* Text */}
        {selectedFile ? (
          <div className="flex flex-col items-center gap-1 px-4 text-center">
            <p className="text-sm font-medium text-foreground truncate max-w-[260px]">
              {selectedFile.name}
            </p>
            <p className="text-xs text-muted-foreground">
              {formatBytes(selectedFile.size)}
            </p>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-1 px-4 text-center">
            <p className="text-sm font-medium text-foreground">
              {isDragging ? "Drop your file here" : "Drag & drop your file here"}
            </p>
            <p className="text-xs text-muted-foreground">
              or click to browse
            </p>
          </div>
        )}

        {/* Hidden input */}
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED_TYPES.join(",")}
          className="hidden"
          onChange={onInputChange}
          disabled={disabled}
        />
      </div>

      {/* Error message */}
      {error && (
        <p className="text-xs text-destructive px-1">{error}</p>
      )}

      {/* Footer row: accepted types + actions */}
      <div className="flex items-center justify-between px-1">
        <p className="text-xs text-muted-foreground">
          Accepts {ACCEPTED_TYPES.join(", ")} · Max {MAX_SIZE_MB} MB
        </p>
        <div className="flex gap-2">
          {selectedFile && (
            <Button
              variant="ghost"
              size="sm"
              onClick={clearFile}
              disabled={disabled}
            >
              Remove
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={() => inputRef.current?.click()}
            disabled={disabled}
          >
            Browse files
          </Button>
        </div>
      </div>
    </div>
  )
}
