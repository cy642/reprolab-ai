import { BookOpenText, RotateCcw } from 'lucide-react'
import type { PaperDetail } from '../../types/paper'
import type { ProtocolParameter } from '../../types/protocol'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { INFO_META, formatDateTime } from './meta'

interface ParameterSourceChainProps {
  parameter: ProtocolParameter
  paper: PaperDetail | null
  onOpenEvidence: (evidenceId: string) => void
  onRestore: (parameter: ProtocolParameter) => void
}

export function ParameterSourceChain({ parameter, paper, onOpenEvidence, onRestore }: ParameterSourceChainProps) {
  const field = paper?.fields.find((item) => item.field === parameter.source_field)
  const evidence = paper?.evidence.find((item) => item.id === parameter.evidence_id)
  const info = INFO_META[parameter.source_type]
  const manuallySupplemented = parameter.source_type === 'unknown' && parameter.value !== null

  return (
    <div className="mt-3 space-y-3" data-testid="parameter-source-chain">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={info.tone}>{info.label}</Badge>
        {manuallySupplemented && <Badge tone="cyan">人工补充</Badge>}
        {parameter.modified_value !== null && <Badge tone="amber">已修改</Badge>}
      </div>

      <div className="rounded-lg border border-white/[.06] bg-canvas/35 p-3">
        <p className="font-mono text-[9px] uppercase tracking-[.14em] text-primary">1 · PAPER FIELD</p>
        <p className="mt-2 text-[11px] text-ink">{parameter.source_field || '无来源字段'}</p>
        <p className="mt-1 text-[10px] text-muted">字段状态：{field?.status || 'unknown'}</p>
      </div>

      <div className="rounded-lg border border-white/[.06] bg-canvas/35 p-3">
        <p className="font-mono text-[9px] uppercase tracking-[.14em] text-accent">2 · PAPER EVIDENCE</p>
        {evidence ? (
          <>
            <button onClick={() => onOpenEvidence(evidence.id)} className="mt-2 flex items-center gap-2 text-[11px] text-accent hover:text-ink">
              <BookOpenText size={13} />PDF 第 {evidence.page} 页 · 查看原文
            </button>
            <p className="mt-2 line-clamp-4 text-[10px] leading-5 text-muted">{evidence.quote}</p>
          </>
        ) : <p className="mt-2 text-[10px] leading-5 text-muted">无有效论文证据，不提供跳转。</p>}
      </div>

      <div className="rounded-lg border border-primary/15 bg-primary/[.035] p-3">
        <p className="font-mono text-[9px] uppercase tracking-[.14em] text-[#C1ADF8]">3 · PROTOCOL PARAMETER</p>
        <div className="mt-3 grid grid-cols-2 gap-2">
          <div>
            <p className="text-[9px] text-muted">论文/生成原值</p>
            <p className="mt-1 break-words font-mono text-[11px] text-ink">{parameter.original_value ?? 'unknown'}</p>
          </div>
          <div>
            <p className="text-[9px] text-muted">当前有效值</p>
            <p className="mt-1 break-words font-mono text-[11px] text-accent">{parameter.value ?? '待补充'}</p>
          </div>
        </div>
        {parameter.modified_value !== null && (
          <Button size="sm" className="mt-3" onClick={() => onRestore(parameter)} icon={<RotateCcw size={12} />}>恢复原值</Button>
        )}
      </div>

      <div>
        <p className="font-mono text-[9px] uppercase tracking-[.14em] text-muted">MODIFICATION HISTORY</p>
        <div className="mt-2 max-h-36 space-y-2 overflow-y-auto">
          {parameter.history.length === 0 && <p className="text-[10px] text-muted">暂无修改记录</p>}
          {[...parameter.history].reverse().map((entry, index) => (
            <div key={`${entry.at}-${index}`} className="rounded border border-white/[.05] p-2 text-[9px] leading-5 text-muted">
              <span className="text-ink">{entry.action === 'restore' ? '恢复原值' : '编辑'}</span> · {formatDateTime(entry.at)}<br />
              {entry.from ?? 'null'} → {entry.to ?? 'null'}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
