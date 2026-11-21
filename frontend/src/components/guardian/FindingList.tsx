import { AlertOctagon, AlertTriangle, CheckCircle2, ChevronDown, Info, Lightbulb, MapPin } from 'lucide-react'
import { Badge, type BadgeTone } from '../ui/Badge'
import type { AuditFinding, FindingStatus, Severity } from '../../types/dataset'

const severityMeta: Record<Severity, { label: string; tone: BadgeTone }> = {
  critical: { label: '严重', tone: 'red' },
  high: { label: '高', tone: 'red' },
  medium: { label: '中', tone: 'amber' },
  low: { label: '低', tone: 'blue' },
  info: { label: '信息', tone: 'neutral' },
}
const statusMeta: Record<FindingStatus, { label: string; tone: BadgeTone }> = {
  confirmed_issue: { label: '规则确认问题', tone: 'red' },
  potential_risk: { label: '潜在风险', tone: 'amber' },
  suggestion: { label: '优化建议', tone: 'blue' },
}

export function FindingList({ findings, expandedId, onToggle }: {
  findings: AuditFinding[]
  expandedId: string | null
  onToggle: (findingId: string) => void
}) {
  if (!findings.length) {
    return <div className="flex flex-col items-center py-16 text-center"><CheckCircle2 size={30} className="text-success" /><p className="mt-3 text-xs text-ink">当前筛选下没有审计发现</p><p className="mt-1 text-[10px] text-muted">规则结果未被 LLM 修改或生成</p></div>
  }
  return (
    <div className="space-y-3">
      {findings.map((finding) => {
        const expanded = expandedId === finding.finding_id
        const records = finding.evidence.records ?? []
        return (
          <article key={finding.finding_id} data-testid="audit-finding" className={`rounded-xl border transition ${expanded ? 'border-white/[.14] bg-canvas/45' : 'border-white/[.055] bg-canvas/25'}`}>
            <button onClick={() => onToggle(finding.finding_id)} className="flex w-full items-center gap-3 p-4 text-left">
              <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${finding.severity === 'critical' || finding.severity === 'high' ? 'bg-danger/10 text-danger' : finding.severity === 'medium' ? 'bg-warning/10 text-warning' : 'bg-blue-400/10 text-blue-300'}`}>
                {finding.status === 'suggestion' ? <Lightbulb size={17} /> : finding.severity === 'info' || finding.severity === 'low' ? <Info size={17} /> : finding.severity === 'critical' ? <AlertOctagon size={17} /> : <AlertTriangle size={17} />}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-xs font-medium text-[#D0D9E6]">{finding.title}</span>
                <span className="mt-1.5 block truncate font-mono text-[9px] text-muted">{finding.rule_id} · {finding.evidence.affected_count ?? finding.affected_rows.length} 条受影响记录</span>
              </span>
              <Badge tone={statusMeta[finding.status].tone} className="hidden lg:inline-flex">{statusMeta[finding.status].label}</Badge>
              <Badge tone={severityMeta[finding.severity].tone}>{severityMeta[finding.severity].label}</Badge>
              <ChevronDown size={15} className={`shrink-0 text-muted transition-transform ${expanded ? 'rotate-180' : ''}`} />
            </button>
            {expanded && (
              <div className="border-t border-white/[.06] px-5 py-4">
                <p className="text-[11px] leading-6 text-[#AAB6C9]">{finding.description}</p>
                <div className="mt-3 rounded-lg border border-primary/10 bg-primary/[.04] p-3 text-[10px] leading-5 text-muted"><span className="text-primary">整改建议：</span>{finding.recommendation}</div>
                <div className="mt-4 flex flex-wrap items-center gap-2 text-[10px] text-muted">
                  <MapPin size={13} className="text-accent" />
                  <span>CSV 行号：{finding.affected_rows.length ? finding.affected_rows.join(', ') : '字段级统计'}</span>
                  {finding.affected_record_ids.length > 0 && <span className="ml-2">记录 ID：{finding.affected_record_ids.join(', ')}</span>}
                </div>
                {records.length > 0 && (
                  <div className="custom-scrollbar mt-4 overflow-x-auto rounded-xl border border-white/[.06]">
                    <table className="w-full min-w-[720px] text-left">
                      <thead><tr className="bg-canvas/60 font-mono text-[9px] uppercase text-muted"><th className="px-3 py-2.5 font-normal">行号</th><th className="px-3 py-2.5 font-normal">记录 ID</th><th className="px-3 py-2.5 font-normal">实体 ID</th><th className="px-3 py-2.5 font-normal">集合</th>{Object.keys(records[0].values).map((column) => <th key={column} className="px-3 py-2.5 font-normal">{column}</th>)}</tr></thead>
                      <tbody className="divide-y divide-white/[.05]">{records.map((record) => <tr key={`${record.row_number}-${record.record_id}`} className="text-[10px] text-[#B9C4D5]"><td className="px-3 py-2.5 font-mono text-accent">{record.row_number}</td><td className="px-3 py-2.5 font-mono">{record.record_id}</td><td className="px-3 py-2.5 font-mono">{record.entity_id || '—'}</td><td className="px-3 py-2.5">{record.split || '—'}</td>{Object.keys(records[0].values).map((column) => <td key={column} className="max-w-36 truncate px-3 py-2.5 font-mono" title={record.values[column]}>{record.values[column] || <span className="text-danger">∅</span>}</td>)}</tr>)}</tbody>
                    </table>
                  </div>
                )}
                {finding.evidence.truncated && <p className="mt-2 text-[9px] text-warning">证据记录已截断展示，完整计数与统计仍由全部数据计算。</p>}
              </div>
            )}
          </article>
        )
      })}
    </div>
  )
}
