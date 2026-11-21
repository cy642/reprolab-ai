import { FileText, LoaderCircle, Quote } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Modal } from '../ui/Modal'
import type { Evidence } from '../../types/paper'
import { getPaperFileUrl } from '../../lib/papers'
import { apiFetch, getDemoAccessCode } from '../../lib/api'
import { HighlightedText } from './HighlightedText'

interface EvidenceModalProps {
  evidence: Evidence | null
  label: string
  pageText: string | null
  loading: boolean
  onClose: () => void
  paperId?: string
}

export function EvidenceModal({ evidence, label, pageText, loading, onClose, paperId }: EvidenceModalProps) {
  const protectedPaper = evidence && getDemoAccessCode() ? paperId : undefined
  const [file, setFile] = useState<{ paper: string; url: string } | null>(null)
  useEffect(() => {
    if (!protectedPaper) return
    const controller = new AbortController()
    let fileUrl = ''
    void apiFetch(`/api/papers/${encodeURIComponent(protectedPaper)}/file`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error('PDF 加载失败')
        const blob = await response.blob()
        if (controller.signal.aborted) return
        fileUrl = URL.createObjectURL(blob)
        setFile({ paper: protectedPaper, url: fileUrl })
      })
      .catch(() => {
        if (!controller.signal.aborted) setFile({ paper: protectedPaper, url: '' })
      })
    return () => {
      controller.abort()
      if (fileUrl) URL.revokeObjectURL(fileUrl)
    }
  }, [protectedPaper])

  const pdfUrl = protectedPaper ? (file?.paper === protectedPaper ? file.url : '') : paperId ? getPaperFileUrl(paperId) : ''
  return (
    <Modal
      open={Boolean(evidence)}
      onClose={onClose}
      title={evidence ? `${label} · 原文证据` : '原文证据'}
      description={evidence ? `PDF 第 ${evidence.page} 页 · 左侧原生跳页，右侧提取文本高亮` : undefined}
      className="max-w-6xl"
    >
      {evidence && (
        <div className={paperId ? 'grid gap-5 lg:grid-cols-2' : ''}>
          {paperId && (
            <section>
              <div className="mb-2 flex items-center gap-2 font-mono text-[9px] uppercase tracking-[.16em] text-accent">
                <FileText size={12} /> Native PDF · Page {evidence.page}
              </div>
              {pdfUrl ? <iframe
                key={`${evidence.id}-${evidence.page}`}
                data-testid="evidence-pdf-frame"
                data-page={evidence.page}
                src={`${pdfUrl}#page=${evidence.page}&view=FitH`}
                title={`PDF 第 ${evidence.page} 页`}
                className="h-[58vh] w-full rounded-xl border border-white/[.08] bg-white"
              /> : <p className="py-8 text-center text-xs text-muted">{file?.paper === protectedPaper ? '无法加载 PDF 原文。' : '正在加载 PDF 原文…'}</p>}
              <p className="mt-2 text-[10px] leading-5 text-muted">原生查看器通过 #page={evidence.page} 定位页码；quote 高亮在右侧提取文本中。</p>
            </section>
          )}
          <section>
            <div className="rounded-xl border border-warning/20 bg-warning/[.05] p-4">
              <div className="flex items-center gap-2 font-mono text-[9px] text-warning">
                <Quote size={12} /> VERIFIED QUOTE
              </div>
              <p className="mt-2 whitespace-pre-wrap text-[13px] leading-7 text-[#E7DDBE]">{evidence.quote}</p>
            </div>

            <div className="mt-4 flex items-center justify-between">
              <p className="font-mono text-[9px] uppercase tracking-[.16em] text-muted">Extracted text · Page {evidence.page}</p>
              {loading && <LoaderCircle size={13} className="animate-spin text-accent" />}
            </div>

            <div className="custom-scrollbar mt-2 max-h-[38vh] overflow-y-auto rounded-xl border border-white/[.06] bg-canvas/55 p-4">
              {pageText ? (
                <div className="whitespace-pre-wrap text-[12px] leading-6 text-[#B9C4D5]">
                  <HighlightedText text={pageText} quote={evidence.quote} />
                </div>
              ) : loading ? (
                <div className="flex h-28 items-center justify-center">
                  <LoaderCircle size={18} className="animate-spin text-accent" />
                </div>
              ) : (
                <p className="py-8 text-center text-xs text-muted">无法加载该页文本。</p>
              )}
            </div>
          </section>
        </div>
      )}
    </Modal>
  )
}
