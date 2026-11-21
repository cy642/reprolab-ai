import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AlertCircle, Cpu, LoaderCircle, RefreshCw, Upload, Sparkles } from 'lucide-react'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { Modal } from '../components/ui/Modal'
import { PageHeader } from '../components/ui/PageHeader'
import { Toast, type ToastTone } from '../components/ui/Toast'
import { EvidenceModal } from '../components/papers/EvidenceModal'
import { PaperDetailView } from '../components/papers/PaperDetail'
import { PaperListPanel } from '../components/papers/PaperListPanel'
import { matchesFilter, type PaperFilter } from '../components/papers/paper-meta'
import { UploadDropzone } from '../components/papers/UploadDropzone'
import { ApiError, deletePaper, getPageText, getPaper, listPapers, parsePaper, uploadPaper } from '../lib/papers'
import { validatePdfFile } from '../lib/pdf-upload'
import type { AIInfo, Evidence, PaperDetail, PaperSummary } from '../types/paper'

interface ToastState {
  message: string
  tone: ToastTone
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) return error.message
  return '操作失败，请稍后重试。'
}

export function PaperIntelligence() {
  const [papers, setPapers] = useState<PaperSummary[]>([])
  const [ai, setAi] = useState<AIInfo | null>(null)
  const [listLoading, setListLoading] = useState(true)
  const [listError, setListError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<PaperDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<PaperFilter>('all')
  const [uploading, setUploading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [parsing, setParsing] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [toast, setToast] = useState<ToastState | null>(null)
  const [pageTexts, setPageTexts] = useState<Record<number, string>>({})
  const [pageLoading, setPageLoading] = useState(false)
  const [activePage, setActivePage] = useState(1)
  const [highlight, setHighlight] = useState<{ page: number; quote: string } | null>(null)
  const [evidenceModal, setEvidenceModal] = useState<{ evidence: Evidence; label: string } | null>(null)
  const headerInputRef = useRef<HTMLInputElement>(null)

  const closeToast = useCallback(() => setToast(null), [])

  const refreshList = useCallback(async (silent = false) => {
    if (!silent) setListLoading(true)
    try {
      const data = await listPapers()
      setPapers(data.items)
      setAi(data.ai)
      setListError(null)
      setSelectedId((current) => (
        current && data.items.some((item) => item.id === current)
          ? current
          : data.items[0]?.id ?? null
      ))
    } catch (error) {
      setListError(errorMessage(error))
    } finally {
      if (!silent) setListLoading(false)
    }
  }, [])

  useEffect(() => {
    void refreshList()
  }, [refreshList])

  useEffect(() => {
    if (!selectedId) {
      setDetail(null)
      return
    }
    const controller = new AbortController()
    setDetailLoading(true)
    setPageTexts({})
    setHighlight(null)
    getPaper(selectedId, controller.signal)
      .then((data) => {
        setDetail(data)
        const firstTextPage = data.pages.find((page) => page.chars > 0)?.page ?? 1
        setActivePage(firstTextPage)
      })
      .catch((error) => {
        if (controller.signal.aborted) return
        setToast({ message: errorMessage(error), tone: 'error' })
        if (error instanceof ApiError && error.status === 404) void refreshList(true)
      })
      .finally(() => {
        if (!controller.signal.aborted) setDetailLoading(false)
      })
    return () => controller.abort()
  }, [selectedId, refreshList])

  useEffect(() => {
    if (!detail || pageTexts[activePage] !== undefined) return
    let cancelled = false
    setPageLoading(true)
    getPageText(detail.id, activePage)
      .then((result) => {
        if (!cancelled) setPageTexts((current) => ({ ...current, [activePage]: result.text }))
      })
      .catch(() => {
        if (!cancelled) setPageTexts((current) => ({ ...current, [activePage]: '' }))
      })
      .finally(() => {
        if (!cancelled) setPageLoading(false)
      })
    return () => { cancelled = true }
  }, [detail, activePage, pageTexts])

  const ensurePageText = useCallback(async (page: number) => {
    if (!detail || pageTexts[page] !== undefined) return
    setPageLoading(true)
    try {
      const result = await getPageText(detail.id, page)
      setPageTexts((current) => ({ ...current, [page]: result.text }))
    } catch {
      setPageTexts((current) => ({ ...current, [page]: '' }))
    } finally {
      setPageLoading(false)
    }
  }, [detail, pageTexts])

  const filteredPapers = useMemo(() => {
    const keyword = query.trim().toLowerCase()
    return papers.filter((paper) => (
      matchesFilter(paper, filter)
      && (!keyword || `${paper.title} ${paper.filename}`.toLowerCase().includes(keyword))
    ))
  }, [papers, filter, query])

  const handleFile = async (file: File) => {
    const validation = validatePdfFile(file)
    if (validation) {
      setToast({ message: validation, tone: 'error' })
      return
    }
    setUploading(true)
    setProgress(0)
    try {
      const uploaded = await uploadPaper(file, setProgress)
      await refreshList(true)
      setSelectedId(uploaded.id)
      if (uploaded.status === 'needs_ocr') {
        setToast({ message: 'PDF 已上传，但未检测到可提取文本，需要 OCR。', tone: 'info' })
        return
      }
      setParsing(true)
      try {
        const parsed = await parsePaper(uploaded.id)
        setDetail(parsed)
        setToast({
          message: parsed.ai_status === 'unconfigured'
            ? '本地启发式解析完成；AI 模型尚未配置。'
            : parsed.ai_status === 'failed'
              ? '模型调用失败，已保留原文与本地提取结果。'
              : '论文结构化解析完成。',
          tone: parsed.ai_status === 'failed' ? 'error' : parsed.ai_status === 'unconfigured' ? 'info' : 'success',
        })
      } finally {
        setParsing(false)
      }
      await refreshList(true)
    } catch (error) {
      if (error instanceof ApiError && error.code === 'duplicate_pdf' && error.paperId) {
        setSelectedId(error.paperId)
        setToast({ message: '该论文已存在，已为你打开已有记录。', tone: 'info' })
      } else {
        setToast({ message: errorMessage(error), tone: 'error' })
      }
    } finally {
      setUploading(false)
      setProgress(0)
    }
  }

  const handleParse = async () => {
    if (!detail) return
    setParsing(true)
    try {
      const parsed = await parsePaper(detail.id)
      setDetail(parsed)
      await refreshList(true)
      setToast({
        message: parsed.parse_message ?? '解析完成。',
        tone: parsed.status === 'needs_ocr' || parsed.ai_status === 'failed' ? 'error' : parsed.ai_status === 'unconfigured' ? 'info' : 'success',
      })
    } catch (error) {
      setToast({ message: errorMessage(error), tone: 'error' })
    } finally {
      setParsing(false)
    }
  }

  const handleDelete = async () => {
    if (!detail) return
    setDeleting(true)
    try {
      await deletePaper(detail.id)
      setConfirmDelete(false)
      setDetail(null)
      setSelectedId(null)
      await refreshList()
      setToast({ message: '论文及相关证据已删除。', tone: 'success' })
    } catch (error) {
      setToast({ message: errorMessage(error), tone: 'error' })
    } finally {
      setDeleting(false)
    }
  }

  const handleExport = () => {
    if (!detail) return
    const blob = new Blob([JSON.stringify(detail, null, 2)], { type: 'application/json;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `${detail.filename.replace(/\.pdf$/i, '')}-extraction.json`
    anchor.click()
    URL.revokeObjectURL(url)
    setToast({ message: '结构化结果已导出为 JSON。', tone: 'success' })
  }

  const openEvidence = (evidence: Evidence, label: string) => {
    setEvidenceModal({ evidence, label })
    setHighlight({ page: evidence.page, quote: evidence.quote })
    void ensurePageText(evidence.page)
  }

  const handleHeaderFile = (file: File | undefined) => {
    if (file) void handleFile(file)
  }

  return (
    <div>
      <PageHeader
        eyebrow="Paper intelligence / Evidence layer"
        title="把论文，读成可执行的复现线索。"
        description="真实上传 PDF、提取逐页原文、结构化论文信息，并为每个字段保留可核验的页码证据。"
        showDemo={false}
        actions={(
          <>
            <input
              ref={headerInputRef}
              type="file"
              accept=".pdf,application/pdf"
              className="hidden"
              onChange={(event) => {
                handleHeaderFile(event.target.files?.[0])
                event.target.value = ''
              }}
            />
            <Button onClick={() => void refreshList()} disabled={listLoading} icon={listLoading ? <LoaderCircle size={15} className="animate-spin" /> : <RefreshCw size={15} />}>刷新</Button>
            <Button variant="primary" onClick={() => headerInputRef.current?.click()} disabled={uploading} icon={<Upload size={15} />}>上传论文</Button>
          </>
        )}
      />

      <AIBanner ai={ai} offline={Boolean(listError && !ai)} />

      <div className="mt-5 grid grid-cols-12 gap-5">
        <div className="col-span-12 space-y-4 xl:col-span-4">
          <Card className="col-span-12" padded={false}>
            <div className="flex items-center gap-2 border-b border-white/[.06] px-4 py-3">
              <p className="font-mono text-[10px] uppercase tracking-[.16em] text-primary">Import PDF</p>
              <span className="ml-auto font-mono text-[9px] text-muted">≤ 20MB</span>
            </div>
            <div className="p-4">
              <UploadDropzone busy={uploading} progress={progress} onFile={handleFile} />
              <p className="mt-3 text-[10px] leading-5 text-[#65728B]">
                上传后自动提取逐页文本并触发解析。扫描件会标记为「需要 OCR」，不会生成虚假字段。
              </p>
            </div>
          </Card>

          <PaperListPanel
            papers={filteredPapers}
            total={papers.length}
            selectedId={selectedId}
            loading={listLoading}
            error={listError}
            query={query}
            filter={filter}
            onQueryChange={setQuery}
            onFilterChange={setFilter}
            onSelect={setSelectedId}
            onRetry={() => void refreshList()}
          />
        </div>

        <PaperDetailView
          key={detail?.id ?? 'empty'}
          detail={detail}
          loading={detailLoading}
          parsing={parsing || uploading}
          onParse={() => void handleParse()}
          onDelete={() => setConfirmDelete(true)}
          onExport={handleExport}
          onOpenEvidence={openEvidence}
          pageText={pageTexts[activePage] ?? null}
          pageLoading={pageLoading}
          activePage={activePage}
          onPageChange={setActivePage}
          highlightQuote={highlight?.page === activePage ? highlight.quote : null}
          onClearHighlight={() => setHighlight(null)}
        />
      </div>

      <EvidenceModal
        evidence={evidenceModal?.evidence ?? null}
        label={evidenceModal?.label ?? ''}
        pageText={evidenceModal ? pageTexts[evidenceModal.evidence.page] ?? null : null}
        loading={pageLoading}
        paperId={detail?.id}
        onClose={() => setEvidenceModal(null)}
      />

      <Modal
        open={confirmDelete}
        onClose={() => { if (!deleting) setConfirmDelete(false) }}
        title="删除这篇论文？"
        description="将删除 PDF 文件、SQLite 记录、结构化字段与全部原文证据，操作不可撤销。"
        className="max-w-md"
      >
        <div className="rounded-xl border border-white/[.06] bg-canvas/45 p-4">
          <p className="text-[13px] font-medium text-ink">{detail?.title || detail?.filename}</p>
          <p className="mt-1.5 font-mono text-[10px] text-muted">{detail?.filename} · {detail?.page_count} 页</p>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setConfirmDelete(false)} disabled={deleting}>取消</Button>
          <Button variant="danger" onClick={() => void handleDelete()} disabled={deleting} icon={deleting ? <LoaderCircle size={15} className="animate-spin" /> : null}>
            {deleting ? '删除中…' : '确认删除'}
          </Button>
        </div>
      </Modal>

      {toast && <Toast message={toast.message} tone={toast.tone} onClose={closeToast} />}
    </div>
  )
}

function AIBanner({ ai, offline }: { ai: AIInfo | null; offline: boolean }) {
  if (offline) {
    return (
      <Card className="border-danger/20 bg-danger/[.035]">
        <div className="flex items-start gap-3">
          <AlertCircle size={18} className="mt-0.5 shrink-0 text-danger" />
          <div>
            <p className="text-xs font-medium text-ink">无法连接论文服务</p>
            <p className="mt-1 text-[11px] leading-5 text-muted">请确认 FastAPI 已在 8000 端口启动；论文数据保存在后端 SQLite 中。</p>
          </div>
        </div>
      </Card>
    )
  }

  if (!ai) return null

  if (!ai.configured) {
    return (
      <Card className="border-warning/15 bg-warning/[.03]">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-warning/20 bg-warning/10 text-warning">
            <Cpu size={17} />
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-xs font-medium text-ink">AI 结构化解析尚未配置</p>
              <Badge tone="amber">LOCAL EXTRACTION ONLY</Badge>
            </div>
            <p className="mt-1 text-[11px] leading-5 text-muted">
              PDF 文本提取、页码预览与本地启发式识别可用；标题、作者、摘要来自原文，其余字段保持待确认。配置后端环境变量
              <code className="mx-1 rounded bg-black/25 px-1 py-0.5 font-mono text-[10px] text-[#E3CE9C]">LLM_BASE_URL / LLM_API_KEY / LLM_MODEL</code>
              并重启服务后启用 AI 解析。
            </p>
          </div>
        </div>
      </Card>
    )
  }

  return (
    <Card className="border-success/15 bg-success/[.025]">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-success/20 bg-success/10 text-success">
          <Sparkles size={17} />
        </div>
        <div className="min-w-0">
          <p className="text-xs font-medium text-ink">AI 解析已配置</p>
          <p className="mt-1 text-[11px] leading-5 text-muted">
            OpenAI 兼容接口已启用，模型 <span className="font-mono text-[#B9C4D5]">{ai.model}</span>。密钥仅保存在后端环境变量中。
          </p>
        </div>
        <Badge tone="green" className="ml-auto">API READY</Badge>
      </div>
    </Card>
  )
}
