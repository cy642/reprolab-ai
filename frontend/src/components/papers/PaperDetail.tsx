import { useState, type ReactNode } from 'react'
import {
  AlertTriangle,
  BookOpenText,
  ChevronLeft,
  ChevronRight,
  Download,
  FileSearch,
  FileText,
  Info,
  LoaderCircle,
  Quote,
  RefreshCw,
  ScanText,
  Trash2,
  X,
} from 'lucide-react'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'
import { formatFileSize } from '../../lib/utils'
import type { Evidence, FieldCategory, PaperDetail, PaperField } from '../../types/paper'
import { CATEGORY_LABELS, FIELD_STATUS, PAPER_STATUS, formatDateTime } from './paper-meta'
import { HighlightedText } from './HighlightedText'

type DetailTab = 'fields' | 'source' | 'evidence'
type CategoryFilter = 'all' | FieldCategory

const SOURCE_LABELS: Record<PaperField['source'], string> = {
  heuristic: '本地启发式',
  llm: 'AI 模型',
  none: '无',
}

interface PaperDetailProps {
  detail: PaperDetail | null
  loading: boolean
  parsing: boolean
  onParse: () => void
  onDelete: () => void
  onExport: () => void
  onOpenEvidence: (evidence: Evidence, label: string) => void
  pageText: string | null
  pageLoading: boolean
  activePage: number
  onPageChange: (page: number) => void
  highlightQuote: string | null
  onClearHighlight: () => void
}

export function PaperDetailView(props: PaperDetailProps) {
  const {
    detail,
    loading,
    parsing,
    onParse,
    onDelete,
    onExport,
    onOpenEvidence,
    pageText,
    pageLoading,
    activePage,
    onPageChange,
    highlightQuote,
    onClearHighlight,
  } = props
  const [tab, setTab] = useState<DetailTab>('fields')
  const [category, setCategory] = useState<CategoryFilter>('all')

  if (loading && !detail) return <DetailSkeleton />

  if (!detail) {
    return (
      <Card className="col-span-12 xl:col-span-8">
        <div className="status-grid flex min-h-[560px] flex-col items-center justify-center rounded-xl border border-white/[.04] p-10 text-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl border border-primary/20 bg-primary/10 text-primary">
            <FileSearch size={24} />
          </div>
          <h2 className="mt-5 font-display text-lg font-semibold text-ink">选择一篇论文开始理解</h2>
          <p className="mt-2 max-w-sm text-xs leading-6 text-muted">
            从左侧论文库选择文档，查看结构化字段、原文页码与证据片段。也可以在左上方拖拽上传新的 PDF。
          </p>
        </div>
      </Card>
    )
  }

  const status = PAPER_STATUS[detail.status]
  const grouped = groupEvidence(detail)
  const visibleFields = detail.fields.filter((field) => category === 'all' || field.category === category)
  const hasParsedContent = detail.fields.some((field) => field.status !== 'unknown')

  return (
    <Card className="col-span-12 animate-fade-up xl:col-span-8" padded={false}>
      <div className="border-b border-white/[.06] p-6">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={status.tone} dot={detail.status === 'extracting'}>{status.label}</Badge>
          <Badge tone={detail.ai_status === 'success' ? 'violet' : detail.ai_status === 'failed' ? 'red' : 'neutral'}>
            {detail.ai_status === 'success' ? 'AI 已解析' : detail.ai_status === 'failed' ? 'AI 调用失败' : 'AI 未参与'}
          </Badge>
          <Badge>{detail.extraction_method === 'hybrid' ? 'AI + 本地' : detail.extraction_method === 'heuristic' ? '本地启发式' : '未解析'}</Badge>
          <span className="ml-auto flex items-center gap-2 font-mono text-[9px] text-muted">
            <span>{detail.page_count} PAGES</span>
            <span className="text-[#3A4761]">·</span>
            <span>{formatFileSize(detail.file_size)}</span>
            <span className="text-[#3A4761]">·</span>
            <span>{formatDateTime(detail.updated_at)}</span>
          </span>
        </div>

        <h2 className="mt-4 max-w-3xl font-display text-[23px] font-semibold leading-[1.35] tracking-[-.025em] text-ink">
          {detail.title || detail.filename}
        </h2>
        <p className="mt-2 truncate font-mono text-[10px] text-muted">{detail.filename} · {detail.pages.length} 页已建立索引</p>

        <div className="mt-5 flex flex-wrap items-center gap-2">
          <Button
            variant={hasParsedContent ? 'secondary' : 'primary'}
            onClick={onParse}
            disabled={parsing || detail.status === 'needs_ocr'}
            icon={parsing ? <LoaderCircle size={15} className="animate-spin" /> : <RefreshCw size={15} />}
          >
            {parsing ? '解析中…' : hasParsedContent ? '重新解析' : '开始解析'}
          </Button>
          <Button variant="secondary" onClick={onExport} icon={<Download size={15} />}>导出 JSON</Button>
          <Button variant="danger" onClick={onDelete} disabled={parsing} icon={<Trash2 size={15} />}>删除</Button>
        </div>
      </div>

      {detail.parse_message && (
        <div className={`mx-6 mt-5 flex items-start gap-3 rounded-xl border p-4 ${
          detail.status === 'needs_ocr'
            ? 'border-warning/20 bg-warning/[.06]'
            : detail.ai_status === 'failed'
              ? 'border-danger/20 bg-danger/[.055]'
              : 'border-accent/15 bg-accent/[.045]'
        }`}>
          {detail.status === 'needs_ocr'
            ? <ScanText size={17} className="mt-0.5 shrink-0 text-warning" />
            : detail.ai_status === 'failed'
              ? <AlertTriangle size={17} className="mt-0.5 shrink-0 text-danger" />
              : <Info size={17} className="mt-0.5 shrink-0 text-accent" />}
          <div className="text-[11px] leading-5">
            <p className="font-medium text-ink">
              {detail.status === 'needs_ocr'
                ? '需要 OCR 后才能结构化解析'
                : detail.ai_status === 'failed'
                  ? '模型调用失败，已保留原文与本地结果'
                  : '解析状态'}
            </p>
            <p className="mt-1 text-muted">{detail.parse_message}</p>
            {detail.ai_error && <p className="mt-1 font-mono text-[10px] text-danger/80">{detail.ai_error}</p>}
          </div>
        </div>
      )}

      {detail.ai_status === 'unconfigured' && detail.status === 'parsed' && (
        <div className="mx-6 mt-3 flex items-start gap-2.5 rounded-xl border border-warning/15 bg-warning/[.04] px-4 py-3 text-[11px] leading-5 text-muted">
          <Info size={15} className="mt-0.5 shrink-0 text-warning" />
          <p>
            AI 模型尚未配置，本次仅使用本地启发式提取。标题、作者、摘要来自 PDF 原文，其余字段保持待确认，不会生成虚假内容。
          </p>
        </div>
      )}

      <div className="mt-5 flex gap-6 border-b border-white/[.06] px-6">
        {([
          ['fields', '结构化信息'],
          ['source', '原文预览'],
          ['evidence', `证据链 ${detail.evidence.length}`],
        ] as Array<[DetailTab, string]>).map(([value, label]) => (
          <button
            key={value}
            onClick={() => setTab(value)}
            className={`relative py-3.5 text-xs transition ${
              tab === value ? 'text-ink after:absolute after:inset-x-0 after:bottom-0 after:h-0.5 after:bg-primary' : 'text-muted hover:text-ink'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="p-6">
        {tab === 'fields' && (
          <div className="animate-fade-up">
            {detail.status === 'needs_ocr' ? (
              <EmptyPanel
                icon={<ScanText size={24} className="text-warning" />}
                title="该 PDF 无法提取文本"
                description="扫描件需要先完成 OCR，生成可检索文本后再上传。系统不会为无文本 PDF 编造字段。"
              />
            ) : !hasParsedContent ? (
              <EmptyPanel
                icon={<BookOpenText size={24} className="text-primary" />}
                title="尚未生成结构化信息"
                description="点击「开始解析」提取标题、作者、摘要等字段；所有结果都会附带 PDF 页码与原文证据。"
                action={<Button variant="primary" size="sm" onClick={onParse} disabled={parsing} icon={parsing ? <LoaderCircle size={14} className="animate-spin" /> : <RefreshCw size={14} />}>{parsing ? '解析中…' : '开始解析'}</Button>}
              />
            ) : (
              <>
                <div className="mb-4 flex flex-wrap gap-1.5">
                  {([['all', '全部字段'], ...Object.entries(CATEGORY_LABELS)] as Array<[CategoryFilter, string]>).map(([value, label]) => (
                    <button
                      key={value}
                      onClick={() => setCategory(value)}
                      className={`rounded-lg border px-2.5 py-1.5 text-[10px] transition ${
                        category === value
                          ? 'border-primary/40 bg-primary/10 text-[#C9B7FA]'
                          : 'border-white/[.06] bg-white/[.025] text-muted hover:text-ink'
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  {visibleFields.map((field) => (
                    <FieldCard key={field.field} field={field} onOpenEvidence={onOpenEvidence} />
                  ))}
                </div>
              </>
            )}
          </div>
        )}

        {tab === 'source' && (
          <div className="animate-fade-up">
            <div className="flex flex-wrap items-center gap-2">
              <button
                onClick={() => onPageChange(Math.max(1, activePage - 1))}
                disabled={activePage <= 1}
                className="rounded-lg border border-line p-1.5 text-muted transition hover:text-ink disabled:opacity-40"
                aria-label="上一页"
              >
                <ChevronLeft size={14} />
              </button>
              <select
                value={activePage}
                onChange={(event) => onPageChange(Number(event.target.value))}
                className="rounded-lg border border-line bg-canvas/70 px-2.5 py-1.5 font-mono text-[11px] text-ink outline-none"
                aria-label="选择页码"
              >
                {detail.pages.map((page) => (
                  <option key={page.page} value={page.page}>第 {page.page} 页 · {page.chars} 字符</option>
                ))}
              </select>
              <button
                onClick={() => onPageChange(Math.min(detail.page_count, activePage + 1))}
                disabled={activePage >= detail.page_count}
                className="rounded-lg border border-line p-1.5 text-muted transition hover:text-ink disabled:opacity-40"
                aria-label="下一页"
              >
                <ChevronRight size={14} />
              </button>
              <span className="font-mono text-[9px] text-muted">REAL PAGE INDEX · {activePage}/{detail.page_count}</span>
              {highlightQuote && (
                <button
                  onClick={onClearHighlight}
                  className="ml-auto flex items-center gap-1.5 rounded-md border border-warning/25 bg-warning/10 px-2 py-1 text-[10px] text-warning"
                >
                  <Quote size={11} /> 已高亮证据
                  <X size={11} />
                </button>
              )}
            </div>

            <div className="custom-scrollbar mt-4 max-h-[560px] overflow-y-auto rounded-xl border border-white/[.06] bg-canvas/45 p-5">
              {pageLoading && !pageText ? (
                <div className="flex h-40 items-center justify-center"><LoaderCircle size={20} className="animate-spin text-accent" /></div>
              ) : pageText ? (
                <div className="whitespace-pre-wrap text-[13px] leading-7 text-[#C3CDDC]">
                  <HighlightedText text={pageText} quote={highlightQuote} />
                </div>
              ) : (
                <div className="flex h-40 flex-col items-center justify-center text-center">
                  <FileText size={22} className="text-[#526078]" />
                  <p className="mt-2 text-xs text-muted">本页没有可提取的文本</p>
                </div>
              )}
            </div>
          </div>
        )}

        {tab === 'evidence' && (
          <div className="animate-fade-up">
            {detail.evidence.length === 0 ? (
              <EmptyPanel
                icon={<Quote size={24} className="text-primary" />}
                title="暂无原文证据"
                description="解析后，每个可确认字段都会附带 PDF 页码与逐字原文片段。点击证据可跳转到对应页面。"
              />
            ) : (
              <div className="space-y-4">
                {grouped.map((group) => (
                  <div key={group.field}>
                    <div className="mb-2 flex items-center gap-2">
                      <p className="text-xs font-medium text-ink">{group.label}</p>
                      <span className="font-mono text-[9px] text-muted">{group.items.length} EVIDENCE</span>
                    </div>
                    <div className="grid gap-2.5 md:grid-cols-2">
                      {group.items.map((item) => (
                        <button
                          key={item.id}
                          onClick={() => onOpenEvidence(item, group.label)}
                          className="group rounded-xl border border-white/[.06] bg-canvas/35 p-4 text-left transition hover:border-primary/25 hover:bg-primary/[.035]"
                        >
                          <div className="flex items-center gap-2">
                            <Badge tone="cyan">P.{item.page}</Badge>
                            <span className="font-mono text-[9px] text-muted">PDF 原文</span>
                            <span className="ml-auto font-mono text-[9px] text-primary opacity-0 transition group-hover:opacity-100">查看原文 →</span>
                          </div>
                          <p className="mt-2.5 line-clamp-4 border-l-2 border-primary/35 pl-3 text-[11px] leading-6 text-[#B7C2D3]">
                            {item.quote}
                          </p>
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </Card>
  )
}

function FieldCard({ field, onOpenEvidence }: {
  field: PaperField
  onOpenEvidence: (evidence: Evidence, label: string) => void
}) {
  const meta = FIELD_STATUS[field.status]
  return (
    <div className={`rounded-xl border p-4 ${
      field.status === 'found'
        ? 'border-white/[.065] bg-canvas/30'
        : field.status === 'pending'
          ? 'border-warning/20 bg-warning/[.03]'
          : 'border-white/[.045] bg-canvas/20'
    }`}>
      <div className="flex items-center gap-2">
        <h3 className="text-xs font-medium text-ink">{field.label}</h3>
        <Badge tone={meta.tone} className="ml-auto">{meta.label}</Badge>
        {field.confidence !== null && field.status !== 'unknown' && (
          <span className="font-mono text-[9px] text-muted">{Math.round(field.confidence * 100)}%</span>
        )}
      </div>
      <p className={`mt-2.5 whitespace-pre-wrap text-[12px] leading-6 ${
        field.value ? 'text-[#B9C4D5]' : 'text-[#65728B]'
      }`}>
        {field.value || '未在原文中找到可验证内容，已标记为待确认。'}
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        <span className="font-mono text-[9px] text-[#5F6C85]">{SOURCE_LABELS[field.source]}</span>
        {field.evidence.map((item) => (
          <button
            key={item.id}
            onClick={() => onOpenEvidence(item, field.label)}
            className="rounded border border-accent/20 bg-accent/[.07] px-1.5 py-0.5 font-mono text-[9px] text-accent transition hover:bg-accent/15"
            title="查看对应 PDF 原文"
          >
            P.{item.page} 证据
          </button>
        ))}
      </div>
    </div>
  )
}

function EmptyPanel({ icon, title, description, action }: {
  icon: ReactNode
  title: string
  description: string
  action?: ReactNode
}) {
  return (
    <div className="status-grid flex min-h-64 flex-col items-center justify-center rounded-xl border border-white/[.05] p-8 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-xl border border-white/[.07] bg-white/[.03]">{icon}</div>
      <p className="mt-4 text-sm text-ink">{title}</p>
      <p className="mt-2 max-w-md text-[11px] leading-6 text-muted">{description}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

function DetailSkeleton() {
  return (
    <Card className="col-span-12 xl:col-span-8">
      <div className="animate-pulse space-y-4">
        <div className="h-3 w-40 rounded bg-white/[.07]" />
        <div className="h-5 w-3/4 rounded bg-white/[.06]" />
        <div className="h-3 w-1/2 rounded bg-white/[.04]" />
        <div className="grid gap-3 pt-6 md:grid-cols-2">
          {[0, 1, 2, 3].map((item) => <div key={item} className="h-28 rounded-xl bg-white/[.035]" />)}
        </div>
      </div>
    </Card>
  )
}

function groupEvidence(detail: PaperDetail) {
  const labels = new Map(detail.fields.map((field) => [field.field, field.label]))
  const groups = new Map<string, Evidence[]>()
  for (const item of detail.evidence) {
    const list = groups.get(item.field) ?? []
    list.push(item)
    groups.set(item.field, list)
  }
  return Array.from(groups.entries()).map(([field, items]) => ({
    field,
    label: labels.get(field) ?? field,
    items,
  }))
}
