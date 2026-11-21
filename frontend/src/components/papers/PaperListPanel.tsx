import { AlertCircle, BookOpenText, LoaderCircle, Search } from 'lucide-react'
import { Badge } from '../ui/Badge'
import { Card } from '../ui/Card'
import { formatFileSize } from '../../lib/utils'
import type { PaperSummary } from '../../types/paper'
import { PAPER_FILTERS, PAPER_STATUS, formatDateTime, type PaperFilter } from './paper-meta'

interface PaperListPanelProps {
  papers: PaperSummary[]
  total: number
  selectedId: string | null
  loading: boolean
  error: string | null
  query: string
  filter: PaperFilter
  onQueryChange: (value: string) => void
  onFilterChange: (value: PaperFilter) => void
  onSelect: (paperId: string) => void
  onRetry: () => void
}

export function PaperListPanel({
  papers,
  total,
  selectedId,
  loading,
  error,
  query,
  filter,
  onQueryChange,
  onFilterChange,
  onSelect,
  onRetry,
}: PaperListPanelProps) {
  return (
    <Card className="col-span-12 xl:col-span-4" padded={false}>
      <div className="border-b border-white/[.06] p-4">
        <div className="relative">
          <Search size={15} className="absolute left-3 top-3 text-muted" />
          <input
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            className="field py-2.5 pl-9 text-xs"
            placeholder="搜索标题或文件名…"
            aria-label="搜索论文"
          />
        </div>
        <div className="custom-scrollbar mt-3 flex gap-1 overflow-x-auto rounded-lg bg-canvas/60 p-1">
          {PAPER_FILTERS.map((item) => (
            <button
              key={item.value}
              onClick={() => onFilterChange(item.value)}
              className={`shrink-0 rounded-md px-2.5 py-1.5 text-[10px] transition ${
                filter === item.value ? 'bg-elevated text-ink shadow-sm' : 'text-muted hover:text-ink'
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      <div className="custom-scrollbar max-h-[640px] divide-y divide-white/[.05] overflow-y-auto">
        {loading && (
          <div className="space-y-3 p-4">
            {[0, 1, 2].map((item) => (
              <div key={item} className="animate-pulse rounded-xl border border-white/[.05] bg-white/[.02] p-4">
                <div className="h-2.5 w-16 rounded bg-white/[.07]" />
                <div className="mt-3 h-3 w-4/5 rounded bg-white/[.06]" />
                <div className="mt-2 h-2.5 w-3/5 rounded bg-white/[.04]" />
              </div>
            ))}
          </div>
        )}

        {!loading && error && (
          <div className="p-8 text-center">
            <AlertCircle size={25} className="mx-auto text-danger" />
            <p className="mt-3 text-xs leading-5 text-muted">{error}</p>
            <button onClick={onRetry} className="mt-3 text-[11px] text-primary">重新加载</button>
          </div>
        )}

        {!loading && !error && papers.map((paper) => {
          const status = PAPER_STATUS[paper.status]
          const active = selectedId === paper.id
          return (
            <button
              key={paper.id}
              onClick={() => onSelect(paper.id)}
              className={`w-full border-l-2 p-4 text-left transition hover:bg-white/[.025] ${
                active ? 'border-l-primary bg-primary/[.055]' : 'border-l-transparent'
              }`}
            >
              <div className="flex items-center gap-2">
                <Badge tone={status.tone} dot={paper.status === 'extracting'}>{status.label}</Badge>
                {paper.ai_status === 'success' && <Badge tone="violet">AI</Badge>}
                {paper.ai_status === 'failed' && <Badge tone="red">AI 失败</Badge>}
                <span className="ml-auto font-mono text-[9px] text-muted">{paper.page_count}P</span>
              </div>
              <h3 className="mt-2.5 line-clamp-2 font-display text-[13px] font-medium leading-5 text-[#D3DCEA]">
                {paper.title || paper.filename}
              </h3>
              <p className="mt-1.5 truncate font-mono text-[9px] text-muted">{paper.filename}</p>
              <div className="mt-2.5 flex items-center gap-2 font-mono text-[9px] text-[#75839B]">
                <span>{formatFileSize(paper.file_size)}</span>
                <span className="text-[#3A4761]">·</span>
                <span>{formatDateTime(paper.created_at)}</span>
                {paper.text_chars === 0 && <span className="ml-auto text-warning">NO TEXT</span>}
              </div>
            </button>
          )
        })}

        {!loading && !error && papers.length === 0 && (
          <div className="p-10 text-center">
            <BookOpenText size={26} className="mx-auto text-[#526078]" />
            <p className="mt-3 text-xs text-muted">
              {total === 0 ? '论文库还是空的' : '没有匹配的论文'}
            </p>
            <p className="mt-1.5 text-[10px] leading-5 text-[#65728B]">
              {total === 0 ? '上传 PDF 后，解析状态会实时显示在这里。' : '调整搜索词或筛选条件。'}
            </p>
          </div>
        )}
      </div>

      <div className="flex items-center justify-between border-t border-white/[.06] px-4 py-3 font-mono text-[9px] text-muted">
        <span>{papers.length} / {total} DOCUMENTS</span>
        {loading && <LoaderCircle size={12} className="animate-spin text-accent" />}
      </div>
    </Card>
  )
}
