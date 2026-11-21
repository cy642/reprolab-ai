import type { BadgeTone } from '../ui/Badge'
import type { InformationType, StepStatus } from '../../types/protocol'

export const STATUS_META: Record<StepStatus, { label: string; tone: BadgeTone }> = {
  planned: { label: '待执行', tone: 'neutral' },
  running: { label: '执行中', tone: 'cyan' },
  done: { label: '已完成', tone: 'green' },
  blocked: { label: '已阻塞', tone: 'red' },
}

export const INFO_META: Record<InformationType, { label: string; tone: BadgeTone }> = {
  paper_fact: { label: '论文事实', tone: 'green' },
  derived_suggestion: { label: 'AI 建议', tone: 'violet' },
  unknown: { label: '待确认', tone: 'amber' },
}

export const PROTOCOL_STATUS: Record<string, { label: string; tone: BadgeTone }> = {
  generated: { label: '已生成', tone: 'cyan' },
  saved: { label: '已保存', tone: 'green' },
  draft: { label: '草稿', tone: 'neutral' },
  archived: { label: '已归档', tone: 'neutral' },
}

export function formatDateTime(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  }).format(date)
}
