import { useRef, useState, type DragEvent } from 'react'
import { FileUp, LoaderCircle, UploadCloud } from 'lucide-react'
import { ProgressBar } from '../ui/ProgressBar'

interface UploadDropzoneProps {
  busy: boolean
  progress: number
  onFile: (file: File) => void
}

export function UploadDropzone({ busy, progress, onFile }: UploadDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setDragging(false)
    if (busy) return
    const file = event.dataTransfer.files[0]
    if (file) onFile(file)
  }

  return (
    <div
      onDragOver={(event) => { event.preventDefault(); if (!busy) setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      className={`relative overflow-hidden rounded-xl border border-dashed p-5 text-center transition ${
        dragging ? 'border-primary/70 bg-primary/[.07]' : 'border-line/90 bg-canvas/35 hover:border-primary/40'
      }`}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,application/pdf"
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0]
          if (file) onFile(file)
          event.target.value = ''
        }}
      />
      {busy ? (
        <div className="py-1">
          <LoaderCircle size={24} className="mx-auto animate-spin text-accent" />
          <p className="mt-3 text-xs text-ink">正在上传并提取 PDF 文本</p>
          <ProgressBar value={progress} color="cyan" className="mx-auto mt-3 w-40" />
          <p className="mt-2 font-mono text-[10px] text-muted">{progress}% · 上传完成后自动解析</p>
        </div>
      ) : (
        <>
          <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-xl border border-primary/20 bg-primary/10 text-primary">
            {dragging ? <FileUp size={19} /> : <UploadCloud size={19} />}
          </div>
          <p className="mt-3 text-xs text-ink">拖拽 PDF 到这里，或点击选择文件</p>
          <p className="mt-1.5 font-mono text-[9px] text-muted">PDF ONLY · MAX 20MB</p>
          <button
            onClick={() => inputRef.current?.click()}
            className="mt-3 rounded-lg border border-primary/35 bg-primary/10 px-3 py-1.5 text-[11px] text-[#C9B7FA] transition hover:bg-primary/15"
          >
            选择 PDF 文件
          </button>
        </>
      )}
    </div>
  )
}
