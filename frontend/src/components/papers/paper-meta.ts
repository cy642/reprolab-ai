import type { BadgeTone } from '../ui/Badge'
import type { FieldCategory, FieldStatus, PaperStatus, PaperSummary } from '../../types/paper'

export type PaperFilter = 'all' | 'parsed' | 'pending' | 'needs_ocr' | 'failed'

export const PAPER_FILTERS: Array<{ value: PaperFilter; label: string }> = [
  { value: 'all', label: '全部' },
  { value: 'parsed', label: '已解析' },
  { value: 'pending', label: '待解析' },
  { value: 'needs_ocr', label: '需 OCR' },
  { value: 'failed', label: '失败' },
]

export function matchesFilter(paper: PaperSummary, filter: PaperFilter): boolean {
  if (filter === 'all') return true
  if (filter === 'pending') return paper.status === 'uploaded' || paper.status === 'extracting'
  return paper.status === filter
}


export const PAPER_STATUS: Record<PaperStatus, { label: string; tone: BadgeTone }> = {
  uploaded: { label: '待解析', tone: 'neutral' },
  extracting: { label: '解析中', tone: 'cyan' },
  parsed: { label: '已解析', tone: 'green' },
  needs_ocr: { label: '需要 OCR', tone: 'amber' },
  failed: { label: '解析失败', tone: 'red' },
}

export const FIELD_STATUS: Record<FieldStatus, { label: string; tone: BadgeTone }> = {
  found: { label: '已提取', tone: 'green' },
  pending: { label: '待确认', tone: 'amber' },
  unknown: { label: '未找到', tone: 'neutral' },
}

export const CATEGORY_LABELS: Record<FieldCategory, string> = {
  basics: '基础信息',
  research: '研究设计',
  experiment: '实验配置',
  outcome: '结论与局限',
}

export function formatDateTime(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}
